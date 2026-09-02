import json
import sqlite3
from io import BytesIO
from pathlib import Path

from loredock.application import LoreDockService


def test_library_source_search_read_delete_round_trip(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path)
    library = service.create_library("产品资料")

    source, job, duplicate = service.import_source(
        library.id,
        "guide.md",
        "text/markdown",
        BytesIO("# 安全\n\n远程 MCP 必须使用 HTTPS 和身份认证。".encode()),
    )

    assert source.status == "ready"
    assert job.status == "succeeded"
    assert duplicate is False
    results = service.search(library.id, "远程 MCP 安全")
    assert results[0].source_id == source.id
    content = service.read_source(source.id, results[0].char_start, results[0].char_end)
    assert content.text == results[0].text

    same_source, same_job, duplicate = service.import_source(
        library.id,
        "copy.md",
        "text/markdown",
        BytesIO("# 安全\n\n远程 MCP 必须使用 HTTPS 和身份认证。".encode()),
    )
    assert duplicate is True
    assert same_source.id == source.id
    assert same_job.id == job.id
    assert len(service.list_sources(library.id)) == 1

    service.close()
    service = LoreDockService(tmp_path)
    assert service.get_library(library.id).name == "产品资料"
    assert service.search(library.id, "HTTPS")[0].source_id == source.id

    service.delete_source(source.id)
    assert service.search(library.id, "HTTPS") == []
    service.delete_library(library.id)
    service.close()


def test_old_index_contract_is_rebuilt_without_changing_source(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path)
    library = service.create_library("Migration")
    source, _, _ = service.import_source(
        library.id,
        "guide.md",
        "text/markdown",
        BytesIO(b"# Migration\n\nrebuildable derived index"),
    )
    paths = service.layout.library(library.id)
    manifest = json.loads(paths.manifest.read_text(encoding="utf-8"))
    manifest["schema_version"] = 2
    paths.manifest.write_text(json.dumps(manifest), encoding="utf-8")

    results = service.search(library.id, "derived index", lexical_only=True)

    assert results[0].source_id == source.id
    assert service.get_source(source.id).content_hash == source.content_hash
    connection = sqlite3.connect(paths.index)
    try:
        version = connection.execute(
            "SELECT value FROM index_metadata WHERE key='schema_version'"
        ).fetchone()
    finally:
        connection.close()
    assert version == ("3",)
    assert json.loads(paths.manifest.read_text(encoding="utf-8"))["schema_version"] == 3
    service.close()
