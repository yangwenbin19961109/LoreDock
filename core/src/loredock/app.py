"""FastAPI application factory."""

import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware

from loredock.api.routes import router
from loredock.application import LoreDockService
from loredock.application.errors import AppError
from loredock.config import Settings
from loredock.mcp.credentials import ReadGrantStore
from loredock.mcp.discovery import clear_endpoint, publish_endpoint
from loredock.mcp.routes import router as agent_router
from loredock.retrieval.model_assets import load_e5_provider, validate_e5_package
from loredock.storage.agent_connections import AgentConnectionStore
from loredock.storage.credential_vault import CredentialVault, LazySystemVault
from loredock.version import __version__


def create_app(
    *, data_dir: Path | None = None, credential_vault: CredentialVault | None = None
) -> FastAPI:
    """Build a fresh application for production and tests."""

    settings = Settings() if data_dir is None else Settings(data_dir=data_dir)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        data_root = settings.resolved_data_dir()
        model_dir = (
            settings.model_dir.resolve()
            if settings.model_dir is not None
            else data_root / "models" / "multilingual-e5-small"
        )
        provider = None
        if settings.model_dir is not None:
            provider = load_e5_provider(model_dir)
        elif model_dir.exists():
            try:
                validate_e5_package(model_dir)
                provider = load_e5_provider(model_dir)
            except ValueError:
                provider = None
        application.state.service = LoreDockService(data_root, provider=provider)
        connections: AgentConnectionStore | None = None
        endpoint_id: str | None = None
        try:
            if settings.desktop_token is not None:
                settings.assert_safe_bind_host()
                connections = await run_in_threadpool(
                    AgentConnectionStore,
                    data_root / "agent-connections.sqlite",
                    credential_vault or LazySystemVault(),
                )
                application.state.agent_connections = connections
                host = "[::1]" if settings.host == "::1" else "127.0.0.1"
                endpoint = await run_in_threadpool(
                    publish_endpoint, data_root, f"http://{host}:{settings.port}"
                )
                endpoint_id = endpoint.instance_id
            yield
        finally:
            if endpoint_id is not None:
                await run_in_threadpool(clear_endpoint, data_root, endpoint_id)
            if connections is not None:
                await run_in_threadpool(connections.close)
            application.state.agent_connections = None
            application.state.service.close()

    app = FastAPI(
        title="LoreDock Core API",
        summary="Local-first knowledge hub application core",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.desktop_shutdown = None
    app.state.read_grants = ReadGrantStore()
    app.state.agent_owner_enabled = settings.desktop_token is not None
    app.state.agent_connections = None

    if settings.desktop_token is not None:
        expected_token = settings.desktop_token.get_secret_value()

        @app.middleware("http")
        async def _authenticate_desktop_request(  # pyright: ignore[reportUnusedFunction]
            request: Request, call_next: RequestResponseEndpoint
        ) -> Response:
            if request.method == "OPTIONS":
                return await call_next(request)
            # Only this exact endpoint uses dedicated read credentials. It has
            # its own mandatory auth dependency; no general API bypass exists.
            if request.url.path == "/api/v1/agent-tools/call":
                return await call_next(request)
            authorization = request.headers.get("authorization", "")
            scheme, _, supplied_token = authorization.partition(" ")
            if (
                scheme.lower() != "bearer"
                or not supplied_token.isascii()
                or not secrets.compare_digest(supplied_token, expected_token)
            ):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "code": "desktop_auth_required",
                            "message": "Desktop Core authentication is required.",
                        }
                    },
                )
            return await call_next(request)

        app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://tauri.localhost",
                "https://tauri.localhost",
                "http://127.0.0.1:1421",
                "http://localhost:1421",
            ],
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.exception_handler(AppError)
    async def _handle_app_error(  # pyright: ignore[reportUnusedFunction]
        _request: Request, error: AppError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(  # pyright: ignore[reportUnusedFunction]
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        fields: dict[str, list[str]] = {}
        for item in error.errors():
            location = ".".join(str(part) for part in item["loc"] if part not in {"body", "query"})
            fields.setdefault(location or "request", []).append(str(item["msg"]))
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "The request could not be validated.",
                    "fields": fields,
                }
            },
        )

    app.include_router(router)
    app.include_router(agent_router)
    return app


app = create_app()
