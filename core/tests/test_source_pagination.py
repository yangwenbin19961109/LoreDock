from pathlib import Path
from typing import Protocol, cast

from fastapi.testclient import TestClient
from httpx import Response

from loredock.app import create_app
from loredock.application import LoreDockService


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: object) -> Response: ...

    def post(self, url: str, **kwargs: object) -> Response: ...


def test_source_list_uses_stable_filtered_cursor_pages(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path)
    app = create_app(data_dir=tmp_path)
    app.state.service = service
    client = cast(HttpClient, TestClient(app))
    created = client.post("/api/v1/libraries", json={"name": "Paged Library"})
    library_id = str(created.json()["id"])

    for name in ["delta.txt", "alpha.md", "charlie.txt", "bravo.md"]:
        response = client.post(
            f"/api/v1/libraries/{library_id}/sources",
            files={"file": (name, f"Unique content for {name}", "text/plain")},
        )
        assert response.status_code == 201

    first = client.get(
        f"/api/v1/libraries/{library_id}/sources",
        params={"limit": 2, "sort": "name-asc"},
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert [item["name"] for item in first_payload["items"]] == ["alpha.md", "bravo.md"]
    cursor = first_payload["page"]["next_cursor"]
    assert cursor

    second = client.get(
        f"/api/v1/libraries/{library_id}/sources",
        params={"limit": 2, "sort": "name-asc", "cursor": cursor},
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert [item["name"] for item in second_payload["items"]] == [
        "charlie.txt",
        "delta.txt",
    ]
    assert second_payload["page"]["next_cursor"] is None

    filtered = client.get(
        f"/api/v1/libraries/{library_id}/sources",
        params={"filter": ".md", "sort": "name-asc"},
    )
    assert [item["name"] for item in filtered.json()["items"]] == ["alpha.md", "bravo.md"]

    mismatched = client.get(
        f"/api/v1/libraries/{library_id}/sources",
        params={"sort": "size-desc", "cursor": cursor},
    )
    assert mismatched.status_code == 400
    assert mismatched.json()["error"]["code"] == "invalid_cursor"
    service.close()
