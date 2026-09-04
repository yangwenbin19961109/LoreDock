from pathlib import Path
from typing import Protocol, cast

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from loredock.app import create_app
from loredock.mcp.credentials import ReadGrantStore


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: object) -> Response: ...
    def post(self, url: str, **kwargs: object) -> Response: ...
    def delete(self, url: str, **kwargs: object) -> Response: ...


def test_read_token_is_scoped_revocable_and_not_an_owner_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOREDOCK_DESKTOP_TOKEN", "fixture-owner")
    owner = {"Authorization": "Bearer fixture-owner"}
    with TestClient(create_app(data_dir=tmp_path)) as raw_client:
        client = cast(HttpClient, raw_client)
        library = client.post("/api/v1/libraries", headers=owner, json={"name": "Allowed"}).json()
        other = client.post("/api/v1/libraries", headers=owner, json={"name": "Private"}).json()
        issued = client.post(
            "/api/v1/agent-grants", headers=owner, json={"library_ids": [library["id"]]}
        )
        assert issued.status_code == 200 and issued.headers["cache-control"] == "no-store"
        grant = issued.json()
        agent = {"Authorization": f"Bearer {grant['token']}"}
        call: dict[str, object] = {"name": "list_libraries", "arguments": {}}
        assert client.post("/api/v1/agent-tools/call", json=call).status_code == 401
        assert client.post("/api/v1/agent-tools/call", headers=owner, json=call).status_code == 401
        result = client.post("/api/v1/agent-tools/call", headers=agent, json=call)
        assert result.json()["data"]["items"] == [{"id": library["id"], "name": "Allowed"}]
        denied = client.post(
            "/api/v1/agent-tools/call",
            headers=agent,
            json={"name": "get_index_status", "arguments": {"library_id": other["id"]}},
        )
        assert denied.json()["is_error"] and denied.json()["data"]["code"] == "access_denied"
        assert (
            client.post("/api/v1/libraries", headers=agent, json={"name": "No"}).status_code == 401
        )
        assert client.post("/api/v1/desktop/shutdown", headers=agent).status_code == 401
        assert (
            client.post(
                "/api/v1/agent-grants", headers=agent, json={"library_ids": [other["id"]]}
            ).status_code
            == 401
        )
        assert (
            client.delete(f"/api/v1/agent-grants/{grant['id']}", headers=owner).status_code == 204
        )
        assert client.post("/api/v1/agent-tools/call", headers=agent, json=call).status_code == 401


def test_agent_endpoint_is_closed_without_desktop_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOREDOCK_DESKTOP_TOKEN", raising=False)
    with TestClient(create_app(data_dir=tmp_path)) as raw_client:
        client = cast(HttpClient, raw_client)
        assert client.post("/api/v1/agent-grants", json={"library_ids": ["id"]}).status_code == 403
        assert (
            client.post(
                "/api/v1/agent-tools/call", json={"name": "list_libraries", "arguments": {}}
            ).status_code
            == 401
        )


def test_tool_body_budget_and_invalid_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOREDOCK_DESKTOP_TOKEN", "fixture-owner")
    with TestClient(create_app(data_dir=tmp_path)) as raw_client:
        client = cast(HttpClient, raw_client)
        owner = {"Authorization": "Bearer fixture-owner"}
        library = client.post("/api/v1/libraries", headers=owner, json={"name": "Fixture"}).json()
        grant = client.post(
            "/api/v1/agent-grants", headers=owner, json={"library_ids": [library["id"]]}
        ).json()
        headers = {"Authorization": f"Bearer {grant['token']}"}
        assert (
            client.post(
                "/api/v1/agent-tools/call", headers=headers, content=b"x" * 32769
            ).status_code
            == 413
        )
        assert (
            client.post(
                "/api/v1/agent-tools/call", headers=headers, content=b"not json"
            ).status_code
            == 422
        )
        rejected = client.post(
            "/api/v1/agent-tools/call",
            headers=headers,
            json={"name": "delete_source", "arguments": {}},
        )
        assert rejected.json()["data"]["code"] == "unknown_tool"


def test_grants_do_not_survive_a_new_store() -> None:
    store = ReadGrantStore()
    grant, token = store.issue(frozenset({"library"}))
    assert store.resolve(token) == grant
    assert ReadGrantStore().resolve(token) is None
    store.revoke(grant.id)
    assert store.resolve(token) is None


def test_owner_lists_only_safe_named_grant_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOREDOCK_DESKTOP_TOKEN", "fixture-owner")
    owner = {"Authorization": "Bearer fixture-owner"}
    with TestClient(create_app(data_dir=tmp_path)) as raw_client:
        client = cast(HttpClient, raw_client)
        library = client.post("/api/v1/libraries", headers=owner, json={"name": "Fixture"}).json()
        grant = client.post(
            "/api/v1/agent-grants",
            headers=owner,
            json={"library_ids": [library["id"]], "name": " Test connection "},
        ).json()
        response = client.get("/api/v1/agent-grants", headers=owner)
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["name"] == "Test connection" and item["created_at"]
        assert set(item) == {"id", "library_ids", "name", "created_at"}
        assert grant["token"] not in response.text
        assert response.headers["cache-control"] == "no-store"
        agent = {"Authorization": f"Bearer {grant['token']}"}
        assert client.get("/api/v1/agent-grants", headers=agent).status_code == 401
        assert (
            client.post(
                "/api/v1/agent-grants",
                headers=owner,
                json={"library_ids": [library["id"]], "name": "   "},
            ).status_code
            == 400
        )
        client.delete(f"/api/v1/agent-grants/{grant['id']}", headers=owner)
        assert client.get("/api/v1/agent-grants", headers=owner).json()["items"] == []


def test_grant_store_has_a_bounded_connection_count() -> None:
    from loredock.application.errors import AppError

    store = ReadGrantStore()
    for _ in range(100):
        store.issue(frozenset({"library"}))
    with pytest.raises(AppError, match="Revoke"):
        store.issue(frozenset({"library"}))
