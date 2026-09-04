"""Owner-triggered local checks, not an external Agent or stdio handshake test."""

from typing import Literal

from pydantic import Field, model_validator

from loredock.application import LoreDockService
from loredock.application.errors import AppError
from loredock.mcp.contracts import (
    ListLibrariesRequest,
    SearchKnowledgeRequest,
    ToolModel,
)
from loredock.mcp.dispatch import SAFE_ERRORS
from loredock.mcp.service import McpToolService
from loredock.mcp.setup import connection_setup
from loredock.storage.agent_connections import AgentConnectionStore

Stage = Literal["credential", "setup", "libraries", "search", "read"]


class DiagnosticRequest(ToolModel):
    library_id: str | None = Field(default=None, min_length=1, max_length=128)
    query: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def paired_query(self) -> "DiagnosticRequest":
        if (self.library_id is None) != (self.query is None):
            raise ValueError("Both library_id and query are required for a search check")
        return self


class DiagnosticResult(ToolModel):
    scope: Literal["local_core"] = "local_core"
    status: Literal["passed", "no_matches", "failed"]
    stage: Stage
    code: str
    completed: list[Stage]
    hit_count: int = 0
    external_agent_verified: Literal[False] = False


def diagnose_connection(
    core: LoreDockService,
    store: AgentConnectionStore,
    connection_id: str,
    payload: DiagnosticRequest,
) -> DiagnosticResult:
    stage: Stage = "credential"
    completed: list[Stage] = []

    def service() -> McpToolService:
        # Re-resolve authorization before every read; do not retain an old grant.
        grant = store.resolve(store.connection_token(connection_id))
        if grant is None:
            raise AppError("connection_not_found", "Connection unavailable")
        return McpToolService(core, allowed_library_ids=grant.library_ids)

    try:
        service()
        completed.append(stage)
        stage = "setup"
        connection_setup(core.layout.root, connection_id)
        completed.append(stage)
        stage = "libraries"
        service().list_libraries(ListLibrariesRequest(limit=1))
        completed.append(stage)
        if payload.query is None or payload.library_id is None:
            return DiagnosticResult(
                status="passed", stage=stage, code="local_check_passed", completed=completed
            )
        stage = "search"
        hits = service().search_knowledge(
            SearchKnowledgeRequest(
                library_id=payload.library_id, query=payload.query, limit=1, lexical_only=True
            )
        )
        completed.append(stage)
        if not hits.items:
            return DiagnosticResult(
                status="no_matches", stage=stage, code="no_matches", completed=completed
            )
        stage = "read"
        service().read_source(hits.items[0].read_reference)
        completed.append(stage)
        return DiagnosticResult(
            status="passed",
            stage=stage,
            code="local_check_passed",
            completed=completed,
            hit_count=len(hits.items),
        )
    except AppError as error:
        allowed = set(SAFE_ERRORS) | {
            "connection_not_found",
            "credential_missing",
            "credential_store_unavailable",
            "bridge_not_packaged",
        }
        code = error.code if error.code in allowed else "internal_error"
    except Exception:
        code = "internal_error"
    return DiagnosticResult(status="failed", stage=stage, code=code, completed=completed)
