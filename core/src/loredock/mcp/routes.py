"""Protected internal bridge API, not an MCP protocol transport."""

import sys
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field, ValidationError
from starlette.concurrency import run_in_threadpool

from loredock.application import LoreDockService
from loredock.application.errors import AppError
from loredock.mcp.contracts import ToolModel
from loredock.mcp.credentials import ReadGrant, ReadGrantStore
from loredock.mcp.dispatch import ToolReply, call_tool
from loredock.mcp.service import McpToolService
from loredock.mcp.setup import connection_instructions
from loredock.storage.agent_connections import AgentConnectionStore

router = APIRouter(prefix="/api/v1", tags=["agent-bridge"])


class GrantRequest(ToolModel):
    library_ids: list[str] = Field(min_length=1, max_length=100)
    name: str = Field(default="Agent", min_length=1, max_length=120)


class GrantSummary(ToolModel):
    id: str
    library_ids: list[str]
    name: str
    created_at: str


class GrantResponse(GrantSummary):
    token: str


class GrantList(ToolModel):
    items: list[GrantSummary]


class ToolRequest(ToolModel):
    name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, object]


def require_owner(request: Request) -> None:
    # The desktop middleware authenticates these non-bridge routes. Without
    # desktop auth configured, credential administration is unavailable.
    if not request.app.state.agent_owner_enabled:
        raise AppError(
            "agent_admin_unavailable", "Desktop authentication is required.", status_code=403
        )


def require_grant(request: Request) -> ReadGrant:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    store = cast(ReadGrantStore, request.app.state.read_grants)
    grant = store.resolve(token) if scheme.lower() == "bearer" and len(token) <= 256 else None
    persistent = cast(AgentConnectionStore | None, request.app.state.agent_connections)
    if (
        grant is None
        and persistent is not None
        and scheme.lower() == "bearer"
        and len(token) <= 256
    ):
        grant = persistent.resolve(token)
    if grant is None:
        raise AppError(
            "agent_auth_required", "A valid read credential is required.", status_code=401
        )
    return grant


def connection_store(request: Request) -> AgentConnectionStore:
    store = cast(AgentConnectionStore | None, request.app.state.agent_connections)
    if store is None:
        raise AppError(
            "agent_admin_unavailable", "Desktop authentication is required.", status_code=403
        )
    return store


def grant_summary(grant: ReadGrant) -> GrantSummary:
    return GrantSummary(
        id=grant.id,
        library_ids=sorted(grant.library_ids),
        name=grant.name,
        created_at=grant.created_at,
    )


@router.post(
    "/agent-connections", dependencies=[Depends(require_owner)], response_model=GrantSummary
)
def create_connection(payload: GrantRequest, request: Request, response: Response) -> GrantSummary:
    core = cast(LoreDockService, request.app.state.service)
    for library_id in payload.library_ids:
        core.get_library(library_id)
    grant = connection_store(request).issue(frozenset(payload.library_ids), payload.name)
    response.headers["Cache-Control"] = "no-store"
    return grant_summary(grant)


@router.get("/agent-connections", dependencies=[Depends(require_owner)], response_model=GrantList)
def list_connections(request: Request, response: Response) -> GrantList:
    response.headers["Cache-Control"] = "no-store"
    return GrantList(
        items=[grant_summary(grant) for grant in connection_store(request).list_grants()]
    )


class RevokeResult(ToolModel):
    revoked: bool = True
    credential_removed: bool


class ConnectionSetup(ToolModel):
    instructions: str
    runtime: str = "development"


@router.get(
    "/agent-connections/{connection_id}/setup",
    dependencies=[Depends(require_owner)],
    response_model=ConnectionSetup,
)
def get_connection_setup(
    connection_id: str, request: Request, response: Response
) -> ConnectionSetup:
    if not any(grant.id == connection_id for grant in connection_store(request).list_grants()):
        raise AppError(
            "connection_not_found", "Connection does not exist or was revoked.", status_code=404
        )
    core = cast(LoreDockService, request.app.state.service)
    response.headers["Cache-Control"] = "no-store"
    return ConnectionSetup(
        instructions=connection_instructions(core.layout.root, connection_id),
        runtime="packaged" if getattr(sys, "frozen", False) else "development",
    )


@router.delete(
    "/agent-connections/{connection_id}",
    dependencies=[Depends(require_owner)],
    response_model=RevokeResult,
)
def revoke_connection(connection_id: str, request: Request) -> RevokeResult:
    return RevokeResult(credential_removed=connection_store(request).revoke(connection_id))


@router.post("/agent-grants", dependencies=[Depends(require_owner)], response_model=GrantResponse)
def issue_grant(payload: GrantRequest, request: Request, response: Response) -> GrantResponse:
    core = cast(LoreDockService, request.app.state.service)
    for library_id in payload.library_ids:
        core.get_library(library_id)
    store = cast(ReadGrantStore, request.app.state.read_grants)
    name = payload.name.strip()
    if not name:
        raise AppError("invalid_grant_name", "Connection name cannot be empty.")
    grant, token = store.issue(frozenset(payload.library_ids), name)
    response.headers["Cache-Control"] = "no-store"
    return GrantResponse(
        id=grant.id,
        token=token,
        library_ids=sorted(grant.library_ids),
        name=grant.name,
        created_at=grant.created_at,
    )


@router.get("/agent-grants", dependencies=[Depends(require_owner)], response_model=GrantList)
def list_grants(request: Request, response: Response) -> GrantList:
    store = cast(ReadGrantStore, request.app.state.read_grants)
    response.headers["Cache-Control"] = "no-store"
    return GrantList(
        items=[
            GrantSummary(
                id=grant.id,
                library_ids=sorted(grant.library_ids),
                name=grant.name,
                created_at=grant.created_at,
            )
            for grant in store.list_grants()
        ]
    )


@router.delete("/agent-grants/{grant_id}", dependencies=[Depends(require_owner)], status_code=204)
def revoke_grant(grant_id: str, request: Request) -> Response:
    cast(ReadGrantStore, request.app.state.read_grants).revoke(grant_id)
    return Response(status_code=204)


@router.post("/agent-tools/call", response_model=ToolReply)
async def invoke_tool(
    request: Request, grant: Annotated[ReadGrant, Depends(require_grant)]
) -> ToolReply:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 32768:
            raise AppError("request_too_large", "Tool request exceeds 32 KiB.", status_code=413)
    try:
        payload = ToolRequest.model_validate_json(bytes(body))
    except ValidationError as error:
        raise AppError("invalid_arguments", "Tool request is invalid.", status_code=422) from error
    service = McpToolService(
        cast(LoreDockService, request.app.state.service), allowed_library_ids=grant.library_ids
    )
    return await run_in_threadpool(call_tool, service, payload.name, payload.arguments)
