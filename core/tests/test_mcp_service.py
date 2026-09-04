from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from loredock.application import LoreDockService
from loredock.application.errors import AppError
from loredock.mcp.contracts import (
    ListLibrariesRequest,
    ReadSourceRequest,
    SearchKnowledgeRequest,
)
from loredock.mcp.dispatch import REQUEST_MODELS, call_tool
from loredock.mcp.service import McpToolService
from loredock.retrieval import HashingEmbeddingProvider


def test_mcp_authorization_and_citation_round_trip(tmp_path: Path) -> None:
    core = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    try:
        allowed = core.create_library("Public fixture")
        denied = core.create_library("Private fixture")
        source, _, _ = core.import_source(
            allowed.id, "sample.txt", "text/plain", BytesIO(b"BM25 fallback knowledge.")
        )
        tools = McpToolService(core, allowed_library_ids=frozenset({allowed.id}))
        assert McpToolService(core).list_libraries(ListLibrariesRequest()).items == []
        assert [x.id for x in tools.list_libraries(ListLibrariesRequest()).items] == [allowed.id]
        with pytest.raises(AppError, match="Library access"):
            tools.search_knowledge(SearchKnowledgeRequest(library_id=denied.id, query="secret"))
        # A permitted library identifier must not authorize another library's source.
        foreign, _, _ = core.import_source(
            denied.id, "secret.txt", "text/plain", BytesIO(b"private")
        )
        with pytest.raises(AppError, match="Source access"):
            tools.read_source(ReadSourceRequest(library_id=allowed.id, source_id=foreign.id))
        results = tools.search_knowledge(
            SearchKnowledgeRequest(library_id=allowed.id, query="BM25", lexical_only=True)
        )
        hit = results.items[0]
        assert hit.source_id == source.id
        excerpt = tools.read_source(hit.read_reference)
        assert excerpt.text.startswith(hit.text)
        assert excerpt.next_start is None
        page = tools.read_source(
            ReadSourceRequest(library_id=allowed.id, source_id=source.id, length=4)
        )
        assert page.text == "BM25" and page.next_start == 4
        assert str(tmp_path) not in results.model_dump_json()
    finally:
        core.close()


def test_mcp_library_pagination(tmp_path: Path) -> None:
    core = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    try:
        ids = {core.create_library(str(i)).id for i in range(3)}
        tools = McpToolService(core, allowed_library_ids=frozenset(ids))
        first = tools.list_libraries(ListLibrariesRequest(limit=2))
        second = tools.list_libraries(ListLibrariesRequest(after_id=first.next_after_id, limit=2))
        assert {x.id for x in first.items + second.items} == ids
        assert len(first.items) == 2 and second.next_after_id is None
    finally:
        core.close()


def test_mcp_contract_limits() -> None:
    with pytest.raises(ValidationError):
        SearchKnowledgeRequest(library_id="id", query="query", limit=11)
    with pytest.raises(ValidationError):
        ReadSourceRequest(library_id="id", source_id="source", length=8001)
    with pytest.raises(ValidationError):
        SearchKnowledgeRequest.model_validate({"library_id": "id", "query": "q", "write": True})


def test_remaining_tools_and_library_bound_cursor(tmp_path: Path) -> None:
    core = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    try:
        library = core.create_library("allowed")
        other = core.create_library("other")
        tools = McpToolService(core, allowed_library_ids=frozenset({library.id, other.id}))
        empty = call_tool(tools, "get_index_status", {"library_id": library.id})
        assert empty.data["source_count"] == 0 and empty.data["index_present"] is False
        sources = [
            core.import_source(
                library.id, f"sample{i}.txt", "text/plain", BytesIO(f"sample {i}".encode())
            )[0]
            for i in range(3)
        ]
        first = call_tool(tools, "list_sources", {"library_id": library.id, "limit": 2})
        assert not first.is_error
        cursor = first.data["next_cursor"]
        assert isinstance(cursor, str)
        second = call_tool(tools, "list_sources", {"library_id": library.id, "cursor": cursor})
        assert second.data["next_cursor"] is None
        first_items = first.data["items"]
        second_items = second.data["items"]
        assert isinstance(first_items, list) and len(cast(list[object], first_items)) == 2
        assert isinstance(second_items, list) and len(cast(list[object], second_items)) == 1
        crossed = call_tool(tools, "list_sources", {"library_id": other.id, "cursor": cursor})
        assert crossed.is_error and crossed.data["code"] == "invalid_cursor"
        info = call_tool(
            tools, "get_source_info", {"library_id": library.id, "source_id": sources[0].id}
        )
        assert info.data["id"] == sources[0].id and "error" not in info.data
        status = call_tool(tools, "get_index_status", {"library_id": library.id})
        assert status.data["ready_source_count"] == 3
        assert status.data["index_present"] is True
        assert status.data["production_embeddings"] is False
        for name in ("list_sources", "get_index_status", "get_source_info"):
            arguments: dict[str, object] = {"library_id": library.id}
            if name == "get_source_info":
                arguments["source_id"] = sources[0].id
            denied = call_tool(McpToolService(core), name, arguments)
            assert denied.is_error and denied.data["code"] == "access_denied"
        assert call_tool(tools, "delete_source", {}).data["code"] == "unknown_tool"
        assert call_tool(tools, "read_source", {"length": 9000}).data["code"] == "invalid_arguments"
        assert len(REQUEST_MODELS) == 6
    finally:
        core.close()


def test_tool_errors_do_not_return_private_exceptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    try:

        def fail(_library_id: str) -> None:
            raise RuntimeError("private/path and secret token")

        monkeypatch.setattr(core, "get_index_status", fail)
        tools = McpToolService(core, allowed_library_ids=frozenset({"allowed"}))
        reply = call_tool(tools, "get_index_status", {"library_id": "allowed"})
        assert reply.is_error and reply.data["code"] == "internal_error"
        assert "private" not in reply.model_dump_json()
    finally:
        core.close()
