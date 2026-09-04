"""Explicit read-only tool registry and transport-independent error mapping."""

from typing import TYPE_CHECKING

from pydantic import ValidationError

from loredock.application.errors import AppError
from loredock.mcp.contracts import (
    LibraryRequest,
    ListLibrariesRequest,
    ListSourcesRequest,
    ReadSourceRequest,
    SearchKnowledgeRequest,
    SourceInfoRequest,
    ToolModel,
)

if TYPE_CHECKING:
    from loredock.mcp.service import McpToolService

REQUEST_MODELS: dict[str, type[ToolModel]] = {
    "list_libraries": ListLibrariesRequest,
    "search_knowledge": SearchKnowledgeRequest,
    "read_source": ReadSourceRequest,
    "list_sources": ListSourcesRequest,
    "get_source_info": SourceInfoRequest,
    "get_index_status": LibraryRequest,
}

SAFE_ERRORS = {
    "access_denied": "Knowledge access is not permitted.",
    "library_not_found": "The library is unavailable.",
    "source_not_found": "The source is unavailable.",
    "source_not_ready": "The source is not ready to read.",
    "invalid_cursor": "The pagination cursor is invalid.",
    "invalid_query": "The search query is invalid.",
    "invalid_range": "The requested range is invalid.",
}


class ToolReply(ToolModel):
    is_error: bool = False
    data: dict[str, object]


def call_tool(service: "McpToolService", name: str, arguments: dict[str, object]) -> ToolReply:
    """Execute only registered reads; never forward private exception strings."""
    try:
        result: ToolModel
        match name:
            case "list_libraries":
                result = service.list_libraries(ListLibrariesRequest.model_validate(arguments))
            case "search_knowledge":
                result = service.search_knowledge(SearchKnowledgeRequest.model_validate(arguments))
            case "read_source":
                result = service.read_source(ReadSourceRequest.model_validate(arguments))
            case "list_sources":
                result = service.list_sources(ListSourcesRequest.model_validate(arguments))
            case "get_source_info":
                result = service.get_source_info(SourceInfoRequest.model_validate(arguments))
            case "get_index_status":
                result = service.get_index_status(LibraryRequest.model_validate(arguments))
            case _:
                return ToolReply(
                    is_error=True, data={"code": "unknown_tool", "message": "Unknown tool."}
                )
        return ToolReply(data=result.model_dump(mode="json"))
    except ValidationError:
        return ToolReply(
            is_error=True,
            data={"code": "invalid_arguments", "message": "Tool arguments are invalid."},
        )
    except AppError as error:
        code = error.code if error.code in SAFE_ERRORS else "internal_error"
        return ToolReply(
            is_error=True,
            data={"code": code, "message": SAFE_ERRORS.get(code, "The tool could not complete.")},
        )
    except Exception:
        return ToolReply(
            is_error=True,
            data={"code": "internal_error", "message": "The tool could not complete."},
        )
