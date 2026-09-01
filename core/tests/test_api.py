from typing import Protocol, cast

from fastapi.testclient import TestClient
from httpx import Response

from loredock.app import create_app


class HttpTestClient(Protocol):
    def get(self, url: str) -> Response: ...


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
