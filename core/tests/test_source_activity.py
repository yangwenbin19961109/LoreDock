import asyncio
import sqlite3
from io import BytesIO
from pathlib import Path

import httpx
import pytest

from loredock.app import create_app
from loredock.application import LoreDockService
from loredock.retrieval import HashingEmbeddingProvider
from loredock.storage.database import AppDatabase


def test_activity_persistence_idempotence_and_cascade(tmp_path: Path) -> None:
    core = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    library = core.create_library("fixture")
    sources = [
        core.import_source(library.id, f"{i}.txt", "text/plain", BytesIO(str(i).encode()))[0]
        for i in range(3)
    ]
    assert core.list_source_collection("recent")[0] == []
    core.read_source(sources[0].id)
    assert core.list_source_collection("recent")[0] == []
    for source in sources:
        core.set_source_favorite(source.id, True)
        core.record_source_visit(source.id)
    core.set_source_favorite(sources[0].id, True)
    assert core.list_source_collection("favorites")[0][0].id == sources[2].id
    core.record_source_visit(sources[0].id)
    assert core.list_source_collection("recent")[0][0].id == sources[0].id
    page, more = core.list_source_collection("favorites", limit=2)
    assert len(page) == 2 and more
    assert len(core.list_source_collection("favorites", limit=2, offset=2)[0]) == 1
    core.close()
    core = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    try:
        assert core.source_is_favorite(sources[0].id)
        assert len(core.list_source_collection("recent")[0]) == 3
        core.set_source_favorite(sources[0].id, False)
        assert not core.source_is_favorite(sources[0].id)
        assert len(core.list_source_collection("recent")[0]) == 3
        core.delete_source(sources[1].id)
        assert len(core.list_source_collection("recent")[0]) == 2
        core.delete_library(library.id)
        assert core.list_source_collection("favorites")[0] == []
        assert (
            core.database.connection.execute("SELECT COUNT(*) FROM source_activity").fetchone()[0]
            == 0
        )
    finally:
        core.close()


def test_recent_history_cap_does_not_remove_favorites(tmp_path: Path) -> None:
    core = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    try:
        library = core.create_library("fixture")
        source = core.import_source(library.id, "a.txt", "text/plain", BytesIO(b"fixture"))[0]
        core.set_source_favorite(source.id, True)
        core.record_source_visit(source.id)
        for index in range(100):
            identifier = f"fixture-{index}"
            with core.database.transaction() as db:
                db.execute(
                    "INSERT INTO sources("
                    "id, library_id, name, media_type, suffix, status, content_hash, "
                    "size_bytes, source_kind, origin_url, error, created_at, updated_at) "
                    "SELECT ?, library_id, name, media_type, suffix, status, ?, size_bytes, "
                    "source_kind, origin_url, error, created_at, updated_at "
                    "FROM sources WHERE id=?",
                    (identifier, identifier, source.id),
                )
            core.record_source_visit(identifier)
        first, more = core.list_source_collection("recent", limit=50)
        second, end = core.list_source_collection("recent", limit=50, offset=50)
        assert more and not end and len(first + second) == 100
        assert source.id not in {item.id for item in first + second}
        assert core.source_is_favorite(source.id)
    finally:
        core.close()


def test_v4_to_latest_retry_preserves_metadata(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite"
    db = AppDatabase(path)
    db.connection.execute("INSERT INTO libraries VALUES ('fixture', 'Keep', 'date', 'date')")
    db.connection.execute("DROP TABLE source_activity")
    db.connection.execute("PRAGMA user_version=4")
    db.connection.commit()
    db.close()
    for _ in range(2):
        db = AppDatabase(path)
        assert db.connection.execute("PRAGMA user_version").fetchone()[0] == 7
        assert db.connection.execute("SELECT name FROM libraries").fetchone()[0] == "Keep"
        assert db.connection.execute("PRAGMA foreign_key_check").fetchall() == []
        with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
            conn.execute("INSERT INTO source_activity(source_id) VALUES ('missing')")
        db.close()


def test_activity_http_validation_and_desktop_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOREDOCK_DESKTOP_TOKEN", "fixture-owner")

    async def run() -> None:
        app = create_app(data_dir=tmp_path)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            headers = {"Authorization": "Bearer fixture-owner"}
            assert (await client.get("/api/v1/source-collections/recent")).status_code == 401
            library = (
                await client.post("/api/v1/libraries", headers=headers, json={"name": "Test"})
            ).json()
            imported = (
                await client.post(
                    f"/api/v1/libraries/{library['id']}/sources",
                    headers=headers,
                    files={"file": ("a.txt", b"sample", "text/plain")},
                )
            ).json()
            source_id = imported["source"]["id"]
            url = f"/api/v1/sources/{source_id}"
            assert (
                await client.put(url + "/favorite", headers=headers, json={"favorite": "true"})
            ).status_code == 422
            assert (
                await client.put(url + "/favorite", headers=headers, json={"favorite": True})
            ).json() == {"favorite": True}
            assert (await client.post(url + "/visit", headers=headers)).status_code == 204
            result = await client.get("/api/v1/source-collections/recent", headers=headers)
            assert result.headers["cache-control"] == "no-store"
            assert result.json()["items"][0]["id"] == source_id
            assert (
                await client.get("/api/v1/source-collections/recent?limit=51", headers=headers)
            ).status_code == 422
            assert (
                await client.post("/api/v1/sources/missing/visit", headers=headers)
            ).status_code == 404

    asyncio.run(run())
