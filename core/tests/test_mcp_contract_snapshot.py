"""Compatibility baseline: changes require review, not blind snapshot regeneration."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from loredock.mcp.bridge import BridgeClient, create_server
from loredock.mcp.contracts import (
    IndexStatus,
    KnowledgeResults,
    LibraryList,
    SourceExcerpt,
    SourceList,
    SourceSummary,
)
from loredock.mcp.dispatch import REQUEST_MODELS, SAFE_ERRORS

RESULT_MODELS = {
    "list_libraries": LibraryList,
    "search_knowledge": KnowledgeResults,
    "read_source": SourceExcerpt,
    "list_sources": SourceList,
    "get_source_info": SourceSummary,
    "get_index_status": IndexStatus,
}


def test_v1_schema_baseline_and_protocol_discovery() -> None:
    baseline = json.loads(
        (Path(__file__).parent / "fixtures" / "mcp-v1.json").read_text(encoding="utf-8")
    )
    assert baseline["inputs"] == {
        name: model.model_json_schema() for name, model in REQUEST_MODELS.items()
    }
    assert baseline["results"] == {
        name: model.model_json_schema() for name, model in RESULT_MODELS.items()
    }
    assert baseline["service_errors"] == SAFE_ERRORS

    async def run() -> None:
        async with httpx.AsyncClient() as client:
            bridge = BridgeClient(client, "http://127.0.0.1:8000", "fixture")
            async with create_connected_server_and_client_session(create_server(bridge)) as session:
                listed = await session.list_tools()
                assert {tool.name: tool.inputSchema for tool in listed.tools} == baseline["inputs"]
                for tool in listed.tools:
                    assert tool.annotations is not None
                    assert tool.annotations.readOnlyHint is True
                    assert tool.annotations.destructiveHint is False
                    assert tool.annotations.idempotentHint is True
                    assert tool.annotations.openWorldHint is False
                    # Result models are documented, not advertised as MCP outputSchema yet.
                    assert tool.outputSchema is None

    asyncio.run(run())


@pytest.mark.parametrize(
    ("scenario", "code"),
    [
        ("auth", "agent_auth_required"),
        ("redirect", "core_request_failed"),
        ("server", "core_request_failed"),
        ("malformed", "invalid_core_response"),
        ("oversized", "response_too_large"),
        ("timeout", "core_timeout"),
        ("offline", "core_unavailable"),
    ],
)
def test_bridge_error_envelope_is_stable_and_redacted(scenario: str, code: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if scenario == "timeout":
            raise httpx.ReadTimeout("private-marker", request=request)
        if scenario == "offline":
            raise httpx.ConnectError("private-marker", request=request)
        status = {"auth": 401, "redirect": 302, "server": 500}.get(scenario, 200)
        body = "private-marker" if scenario != "oversized" else "x" * 524289
        return httpx.Response(status, text=body)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result = await BridgeClient(client, "http://127.0.0.1:8000", "fixture").call(
                "list_libraries", {}
            )
            assert result.isError is True
            assert result.structuredContent is not None
            assert set(result.structuredContent) == {"code", "message"}
            assert result.structuredContent["code"] == code
            assert len(result.content) == 1
            content = result.content[0]
            assert content.type == "text"
            assert json.loads(content.text) == result.structuredContent
            assert "private-marker" not in result.model_dump_json()

    asyncio.run(run())
