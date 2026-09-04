import asyncio
import sys
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

from loredock.app import create_app
from loredock.mcp.bridge import BridgeClient, create_server, validate_core_url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com:443",
        "http://localhost:8000",
        "http://127.0.0.1:8000/path",
        "http://user:secret@127.0.0.1:8000",
        "http://127.0.0.1:8000?token=x",
    ],
)
def test_bridge_rejects_nonlocal_or_ambiguous_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_core_url(url)


def test_protocol_calls_real_core_with_scoped_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOREDOCK_DESKTOP_TOKEN", "test-owner")

    async def run() -> None:
        app = create_app(data_dir=tmp_path)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
            ) as client,
        ):
            owner = {"Authorization": "Bearer test-owner"}
            library = (
                await client.post("/api/v1/libraries", headers=owner, json={"name": "Test"})
            ).json()
            imported = (
                await client.post(
                    f"/api/v1/libraries/{library['id']}/sources",
                    headers=owner,
                    files={"file": ("test.txt", b"BM25 fallback knowledge", "text/plain")},
                )
            ).json()
            grant = (
                await client.post(
                    "/api/v1/agent-grants", headers=owner, json={"library_ids": [library["id"]]}
                )
            ).json()
            bridge = BridgeClient(client, "http://127.0.0.1:8000", grant["token"])
            async with create_connected_server_and_client_session(create_server(bridge)) as session:
                listed = await session.list_tools()
                assert len(listed.tools) == 6
                assert all(
                    tool.annotations and tool.annotations.readOnlyHint for tool in listed.tools
                )
                result = await session.call_tool(
                    "search_knowledge",
                    {
                        "library_id": library["id"],
                        "query": "BM25",
                        "lexical_only": True,
                    },
                )
                assert not result.isError and result.structuredContent is not None
                read = await session.call_tool(
                    "read_source",
                    {
                        "library_id": library["id"],
                        "source_id": imported["source"]["id"],
                    },
                )
                assert not read.isError and read.structuredContent is not None
                assert read.structuredContent["text"] == "BM25 fallback knowledge"
                invalid = await session.call_tool("read_source", {"secret": "private marker"})
                assert invalid.isError and "private marker" not in invalid.model_dump_json()
                await client.delete(f"/api/v1/agent-grants/{grant['id']}", headers=owner)
                expired = await session.call_tool("list_libraries", {})
                assert expired.isError and expired.structuredContent is not None
                assert expired.structuredContent["code"] == "agent_auth_required"

    asyncio.run(run())


def test_stdio_subprocess_handshake_and_discovery() -> None:
    async def run() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "loredock.mcp.bridge"],
            env={
                "LOREDOCK_BRIDGE_URL": "http://127.0.0.1:8000",
                "LOREDOCK_BRIDGE_TOKEN": "test-only",
            },
        )
        async with (
            stdio_client(parameters) as (read, write),
            ClientSession(read, write) as session,
        ):
            initialized = await session.initialize()
            assert initialized.serverInfo.name == "LoreDock"
            assert len((await session.list_tools()).tools) == 6
            unknown = await session.call_tool("delete_source", {})
            assert unknown.isError

    asyncio.run(asyncio.wait_for(run(), timeout=20))


def test_bridge_does_not_follow_redirect_or_expose_error_body() -> None:
    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    302, headers={"Location": "https://example.com"}, text="secret"
                )
            )
        ) as client:
            result = await BridgeClient(client, "http://127.0.0.1:8000", "test").call(
                "list_libraries", {}
            )
            assert result.isError and "secret" not in result.model_dump_json()

    asyncio.run(run())
