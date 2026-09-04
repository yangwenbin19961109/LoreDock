import asyncio
from pathlib import Path

import httpx
import pytest

from loredock.app import create_app
from loredock.application.errors import AppError
from loredock.mcp.bridge import ProfileBridge
from loredock.mcp.discovery import clear_endpoint, publish_endpoint, read_endpoint
from loredock.storage.agent_connections import AgentConnectionStore


class FakeVault:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.fail_writes = False
        self.fail_deletes = False

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        if self.fail_writes:
            raise RuntimeError("private backend failure")
        self.values[service, username] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.fail_deletes:
            raise RuntimeError
        self.values.pop((service, username), None)


def test_connection_survives_restart_without_plaintext_on_disk(tmp_path: Path) -> None:
    vault = FakeVault()
    path = tmp_path / "connections.sqlite"
    store = AgentConnectionStore(path, vault)
    grant = store.issue(frozenset({"library"}), "Agent connection")
    token = store.connection_token(grant.id)
    store.close()
    assert token.encode() not in path.read_bytes()
    reopened = AgentConnectionStore(path, vault)
    try:
        assert reopened.list_grants() == [grant]
        assert reopened.connection_token(grant.id) == token
        assert reopened.resolve(token) == grant
        assert reopened.revoke(grant.id)
        assert reopened.resolve(token) is None
        with pytest.raises(AppError, match="revoked"):
            reopened.connection_token(grant.id)
    finally:
        reopened.close()


def test_failed_vault_write_never_creates_authorization(tmp_path: Path) -> None:
    vault = FakeVault()
    vault.fail_writes = True
    store = AgentConnectionStore(tmp_path / "connections.sqlite", vault)
    try:
        with pytest.raises(AppError, match="securely save"):
            store.issue(frozenset({"library"}))
        assert store.list_grants() == []
    finally:
        store.close()


def test_revoke_denies_access_even_if_vault_cleanup_fails(tmp_path: Path) -> None:
    vault = FakeVault()
    path = tmp_path / "connections.sqlite"
    store = AgentConnectionStore(path, vault)
    grant = store.issue(frozenset({"library"}))
    token = store.connection_token(grant.id)
    vault.fail_deletes = True
    assert not store.revoke(grant.id)
    assert store.resolve(token) is None
    store.close()
    reopened = AgentConnectionStore(path, vault)
    assert reopened.resolve(token) is None
    reopened.close()


def test_persistent_http_and_bridge_restore_after_core_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = FakeVault()
    monkeypatch.setenv("LOREDOCK_DESKTOP_TOKEN", "owner-fixture")
    monkeypatch.setenv("LOREDOCK_PORT", "49321")

    async def run() -> None:
        owner = {"Authorization": "Bearer owner-fixture"}
        app = create_app(data_dir=tmp_path, credential_vault=vault)
        ports: list[int | None] = []

        async def observe(request: httpx.Request) -> None:
            ports.append(request.url.port)

        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:49321"
            ) as client,
        ):
            library = (
                await client.post("/api/v1/libraries", headers=owner, json={"name": "Fixture"})
            ).json()
            created = await client.post(
                "/api/v1/agent-connections",
                headers=owner,
                json={"library_ids": [library["id"]], "name": "Persistent"},
            )
            assert created.status_code == 200 and "token" not in created.json()
            connection_id = str(created.json()["id"])
            setup = await client.get(
                f"/api/v1/agent-connections/{connection_id}/setup", headers=owner
            )
            assert setup.status_code == 200
            assert connection_id in setup.json()["instructions"]
            assert next(iter(vault.values.values())) not in setup.text
            assert (
                await client.get(f"/api/v1/agent-connections/{connection_id}/setup")
            ).status_code == 401
            bridge = ProfileBridge(client, tmp_path, connection_id, vault)
            assert not (await bridge.call("list_libraries", {})).isError
            assert read_endpoint(tmp_path).url.endswith(":49321")
        assert not (tmp_path / "agent-endpoint.json").exists()
        monkeypatch.setenv("LOREDOCK_PORT", "49322")
        app2 = create_app(data_dir=tmp_path, credential_vault=vault)
        async with (
            app2.router.lifespan_context(app2),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app2),
                base_url="http://127.0.0.1:49322",
                event_hooks={"request": [observe]},
            ) as client2,
        ):
            bridge.client = client2  # Swap only the in-process test transport.
            listing = await client2.get("/api/v1/agent-connections", headers=owner)
            assert listing.json()["items"][0]["id"] == connection_id
            assert not (await bridge.call("list_libraries", {})).isError
            assert ports[-1] == 49322
            token = next(iter(vault.values.values()))
            assert (
                await client2.get(
                    "/api/v1/agent-connections", headers={"Authorization": f"Bearer {token}"}
                )
            ).status_code == 401
            revoked = await client2.delete(
                f"/api/v1/agent-connections/{connection_id}", headers=owner
            )
            assert revoked.json() == {"revoked": True, "credential_removed": True}
            assert (await bridge.call("list_libraries", {})).isError
            response = await client2.post(
                "/api/v1/agent-tools/call",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": "list_libraries", "arguments": {}},
            )
            assert response.status_code == 401

    asyncio.run(run())


def test_discovery_rejects_external_address_and_retains_new_instance(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        publish_endpoint(tmp_path, "http://example.com:8000")
    first = publish_endpoint(tmp_path, "http://127.0.0.1:8000")
    second = publish_endpoint(tmp_path, "http://127.0.0.1:8001")
    clear_endpoint(tmp_path, first.instance_id)
    assert read_endpoint(tmp_path) == second
    clear_endpoint(tmp_path, second.instance_id)
    assert not (tmp_path / "agent-endpoint.json").exists()
