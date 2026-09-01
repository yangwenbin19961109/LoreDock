"""FastAPI application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from loredock.api.routes import router
from loredock.application import LoreDockService
from loredock.application.errors import AppError
from loredock.config import Settings
from loredock.version import __version__


def create_app(*, data_dir: Path | None = None) -> FastAPI:
    """Build a fresh application for production and tests."""

    settings = Settings(data_dir=data_dir)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        application.state.service = LoreDockService(settings.resolved_data_dir())
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
