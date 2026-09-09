import asyncio
from pathlib import Path

import httpx
import pytest
from test_agent_connections import FakeVault

from loredock.app import create_app


def test_owner_diagnostics_are_scoped_bounded_and_do_not_return_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOREDOCK_DESKTOP_TOKEN", "fixture-owner")
    vault = FakeVault()

    async def run() -> None:
        app = create_app(data_dir=tmp_path, credential_vault=vault)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            owner = {"Authorization": "Bearer fixture-owner"}
            library = (
                await client.post("/api/v1/libraries", headers=owner, json={"name": "Fixture"})
            ).json()
            imported = await client.post(
                f"/api/v1/libraries/{library['id']}/sources",
                headers=owner,
                files={
                    "file": ("private-filename.txt", b"unique diagnostic knowledge", "text/plain")
                },
            )
            job_id = imported.json()["job"]["id"]
            job = {"status": "pending"}
            for _ in range(300):
                job = (await client.get(f"/api/v1/jobs/{job_id}", headers=owner)).json()
                if job["status"] not in {"pending", "running"}:
                    break
                await asyncio.sleep(0.01)
            assert job["status"] == "succeeded"
            connection = (
                await client.post(
                    "/api/v1/agent-connections",
                    headers=owner,
                    json={"name": "Test", "library_ids": [library["id"]]},
                )
            ).json()
            url = f"/api/v1/agent-connections/{connection['id']}/diagnostics"
            assert (await client.post(url, json={})).status_code == 401
            token = next(iter(vault.values.values()))
            assert (
                await client.post(url, json={}, headers={"Authorization": f"Bearer {token}"})
            ).status_code == 401
            basic = await client.post(url, headers=owner, json={})
            assert basic.status_code == 200
            assert basic.headers["cache-control"] == "no-store"
            assert basic.json()["completed"] == ["credential", "setup", "libraries"]
            assert basic.json()["external_agent_verified"] is False
            result = await client.post(
                url, headers=owner, json={"library_id": library["id"], "query": "unique"}
            )
            assert result.json()["status"] == "passed"
            assert result.json()["stage"] == "read"
            assert result.json()["hit_count"] == 1
            for private in (token, str(tmp_path), "private-filename", "unique"):
                assert private not in result.text
            empty = await client.post(
                url, headers=owner, json={"library_id": library["id"], "query": "zzzznomatch"}
            )
            assert empty.json()["status"] == "no_matches"
            denied = await client.post(
                url, headers=owner, json={"library_id": "foreign", "query": "x"}
            )
            assert denied.json()["code"] == "access_denied"
            assert denied.json()["stage"] == "search"
            vault.values.clear()
            missing = await client.post(url, headers=owner, json={})
            assert missing.json()["code"] == "credential_missing"
            await client.delete(f"/api/v1/agent-connections/{connection['id']}", headers=owner)
            revoked = await client.post(url, headers=owner, json={})
            assert revoked.json()["code"] == "connection_not_found"

    asyncio.run(run())


@pytest.mark.parametrize(
    "payload",
    [
        {"query": "x"},
        {"library_id": "x"},
        {"query": "", "library_id": "x"},
        {"query": "x" * 2001, "library_id": "x"},
        {"write": True},
    ],
)
def test_diagnostic_request_rejects_invalid_inputs(payload: dict[str, object]) -> None:
    from pydantic import ValidationError

    from loredock.mcp.diagnostics import DiagnosticRequest

    with pytest.raises(ValidationError):
        DiagnosticRequest.model_validate(payload)
