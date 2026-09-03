from pathlib import Path
from typing import Protocol, cast

from fastapi.testclient import TestClient
from httpx import Response

from loredock.app import create_app


class HttpTestClient(Protocol):
    def get(self, url: str) -> Response: ...
    def put(self, url: str, *, json: dict[str, object]) -> Response: ...


def create_test_client() -> HttpTestClient:
    return cast(HttpTestClient, TestClient(create_app()))


def test_health_contract() -> None:
    client = create_test_client()

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "loredock-core",
        "version": "0.1.0",
        "api_version": "v1",
    }


def test_version_contract() -> None:
    client = create_test_client()

    response = client.get("/api/v1/version")

    assert response.status_code == 200
    assert response.json() == {
        "product": "LoreDock",
        "core_version": "0.1.0",
        "api_version": "v1",
    }


def test_settings_are_persisted(tmp_path: Path) -> None:
    with TestClient(create_app(data_dir=tmp_path)) as raw_client:
        client = cast(HttpTestClient, raw_client)
        initial = client.get("/api/v1/settings")
        assert initial.status_code == 200
        assert initial.json()["theme"] == "system"
        updated = client.put(
            "/api/v1/settings",
            json={
                "onboarding_completed": True,
                "theme": "dark",
                "default_search_mode": "lexical",
            },
        )

        assert updated.status_code == 200
        assert updated.json()["onboarding_completed"] is True
        assert client.get("/api/v1/settings").json()["default_search_mode"] == "lexical"


def test_default_model_reports_missing_without_network(tmp_path: Path) -> None:
    with TestClient(create_app(data_dir=tmp_path)) as raw_client:
        client = cast(HttpTestClient, raw_client)
        response = client.get("/api/v1/models/default")

    assert response.status_code == 200
    assert response.json()["state"] == "missing"
    assert response.json()["active"] is False
    assert response.json()["download_size_bytes"] > 0


def test_latest_model_job_is_empty_on_fresh_install(tmp_path: Path) -> None:
    with TestClient(create_app(data_dir=tmp_path)) as raw_client:
        client = cast(HttpTestClient, raw_client)
        response = client.get("/api/v1/models/jobs/latest")

    assert response.status_code == 200
    assert response.json() is None
