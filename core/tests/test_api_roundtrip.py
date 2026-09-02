from pathlib import Path
from typing import Protocol, cast

from fastapi.testclient import TestClient
from httpx import Response

from loredock.app import create_app
from loredock.application import LoreDockService


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: object) -> Response: ...

    def post(self, url: str, **kwargs: object) -> Response: ...

    def delete(self, url: str, **kwargs: object) -> Response: ...


def test_http_api_completes_knowledge_round_trip(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path)
    app = create_app(data_dir=tmp_path)
    app.state.service = service
    client = cast(HttpClient, TestClient(app))

    created = client.post("/api/v1/libraries", json={"name": "API Library"})
    assert created.status_code == 201
    library_id = str(created.json()["id"])

    imported = client.post(
        f"/api/v1/libraries/{library_id}/sources",
        files={"file": ("notes.txt", "LoreDock keeps exact citation ranges.", "text/plain")},
    )
    assert imported.status_code == 201
    source_id = str(imported.json()["source"]["id"])

    searched = client.post(
        f"/api/v1/libraries/{library_id}/search",
        json={"query": "exact citation ranges"},
    )
    assert searched.status_code == 200
    result = searched.json()["items"][0]
    assert result["source_id"] == source_id
    assert result["matched_chunk_id"] == result["chunk_id"]
    assert result["context_id"]
    assert result["matched_range"]["char_start"] == result["char_start"]
    assert "citation ranges" in result["context_text"]

    content = client.get(f"/api/v1/sources/{source_id}/content")
    assert content.status_code == 200
    assert "citation ranges" in content.json()["text"]

    assert client.delete(f"/api/v1/sources/{source_id}").status_code == 204
    assert client.delete(f"/api/v1/libraries/{library_id}").status_code == 204
    service.close()
