"""FastAPI application factory."""

import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware

from loredock.api.routes import router
from loredock.application import LoreDockService
from loredock.application.errors import AppError
from loredock.config import Settings
from loredock.retrieval.model_assets import load_e5_provider
from loredock.version import __version__


def create_app(*, data_dir: Path | None = None) -> FastAPI:
    """Build a fresh application for production and tests."""

    settings = Settings() if data_dir is None else Settings(data_dir=data_dir)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        provider = (
            load_e5_provider(settings.model_dir.resolve())
            if settings.model_dir is not None
            else None
        )
        application.state.service = LoreDockService(settings.resolved_data_dir(), provider=provider)
        try:
            yield
        finally:
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

    if settings.desktop_token is not None:
        expected_token = settings.desktop_token.get_secret_value()

        @app.middleware("http")
        async def _authenticate_desktop_request(  # pyright: ignore[reportUnusedFunction]
            request: Request, call_next: RequestResponseEndpoint
        ) -> Response:
            if request.method == "OPTIONS":
                return await call_next(request)
            authorization = request.headers.get("authorization", "")
            scheme, _, supplied_token = authorization.partition(" ")
            if scheme.lower() != "bearer" or not secrets.compare_digest(
                supplied_token, expected_token
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
            allow_origins=["http://tauri.localhost", "https://tauri.localhost"],
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
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
    return app


app = create_app()
