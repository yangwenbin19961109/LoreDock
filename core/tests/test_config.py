from pathlib import Path
from typing import Protocol, cast

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from loredock.app import create_app
from loredock.config import Settings


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: object) -> Response: ...

    def post(self, url: str, **kwargs: object) -> Response: ...


def test_local_bind_is_allowed() -> None:
    Settings(host="127.0.0.1").assert_safe_bind_host()


def test_non_loopback_bind_is_rejected() -> None:
    with pytest.raises(ValueError, match="loopback"):
        Settings(host="0.0.0.0").assert_safe_bind_host()


def test_application_respects_environment_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOREDOCK_DATA_DIR", str(tmp_path))
    app = create_app()

    with TestClient(app):
        assert app.state.service.layout.root == tmp_path.resolve()


def test_desktop_token_protects_core_and_enables_graceful_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOREDOCK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOREDOCK_DESKTOP_TOKEN", "test-secret")
    app = create_app()
    stopped = False

    def request_shutdown() -> None:
        nonlocal stopped
        stopped = True

    app.state.desktop_shutdown = request_shutdown
    with TestClient(app) as test_client:
        client = cast(HttpClient, test_client)
        unauthorized = client.get("/api/v1/health")
        assert unauthorized.status_code == 401
        assert unauthorized.json()["error"]["code"] == "desktop_auth_required"

        headers = {"Authorization": "Bearer test-secret"}
        assert client.get("/api/v1/health", headers=headers).status_code == 200
        assert client.post("/api/v1/desktop/shutdown", headers=headers).status_code == 202

    assert stopped is True
