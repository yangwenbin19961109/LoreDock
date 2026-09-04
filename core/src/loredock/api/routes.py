"""Versioned HTTP adapter for LoreDock application use cases."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status

from loredock.api.contracts import (
    AppSettingsResponse,
    AppSettingsUpdate,
    FavoriteState,
    HealthResponse,
    JobResponse,
    LibraryCreate,
    LibraryResponse,
    LibraryUpdate,
    ModelJobResponse,
    ModelStatusResponse,
    Page,
    PageInfo,
    SearchRequest,
    SearchResponse,
    SearchResultResponse,
    SourceContentResponse,
    SourceImportResponse,
    SourceResponse,
    VersionResponse,
)
from loredock.api.pagination import SourceCursor, decode_source_cursor, encode_source_cursor
from loredock.application import LoreDockService
from loredock.application.errors import AppError
from loredock.version import API_VERSION, __version__

router = APIRouter(prefix=f"/api/{API_VERSION}")


def get_service(request: Request) -> LoreDockService:
    return request.app.state.service


Service = Annotated[LoreDockService, Depends(get_service)]


@router.get("/sources/{source_id}/favorite", response_model=FavoriteState, tags=["sources"])
def get_favorite(source_id: str, service: Service, response: Response) -> FavoriteState:
    response.headers["Cache-Control"] = "no-store"
    return FavoriteState(favorite=service.source_is_favorite(source_id))


@router.put("/sources/{source_id}/favorite", response_model=FavoriteState, tags=["sources"])
def set_favorite(
    source_id: str, payload: FavoriteState, service: Service, response: Response
) -> FavoriteState:
    response.headers["Cache-Control"] = "no-store"
    return FavoriteState(favorite=service.set_source_favorite(source_id, payload.favorite))


@router.post("/sources/{source_id}/visit", status_code=204, tags=["sources"])
def record_visit(source_id: str, service: Service) -> Response:
    service.record_source_visit(source_id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/source-collections/{kind}", response_model=Page[SourceResponse], tags=["sources"])
def source_collection(
    kind: Literal["recent", "favorites"],
    service: Service,
    response: Response,
    limit: int = Query(default=50, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> Page[SourceResponse]:
    records, more = service.list_source_collection(kind, limit=limit, offset=offset)
    response.headers["Cache-Control"] = "no-store"
    return Page(
        items=[SourceResponse.model_validate(record) for record in records],
        page=PageInfo(limit=limit, next_cursor=str(offset + limit) if more else None),
    )


@router.get("/settings", response_model=AppSettingsResponse, tags=["settings"])
def get_settings(service: Service) -> AppSettingsResponse:
    return AppSettingsResponse.model_validate(service.get_settings())


@router.put("/settings", response_model=AppSettingsResponse, tags=["settings"])
def update_settings(payload: AppSettingsUpdate, service: Service) -> AppSettingsResponse:
    return AppSettingsResponse.model_validate(service.update_settings(**payload.model_dump()))


@router.get("/models/default", response_model=ModelStatusResponse, tags=["models"])
def get_default_model(service: Service) -> ModelStatusResponse:
    return ModelStatusResponse.model_validate(service.get_default_model_status())


@router.get("/models/jobs/latest", response_model=ModelJobResponse | None, tags=["models"])
def latest_model_job(service: Service) -> ModelJobResponse | None:
    job = service.latest_model_job()
    return ModelJobResponse.model_validate(job) if job is not None else None


@router.post(
    "/models/default/install",
    response_model=ModelJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["models"],
)
def install_default_model(service: Service) -> ModelJobResponse:
    return ModelJobResponse.model_validate(service.start_model_install())


@router.get("/models/jobs/{job_id}", response_model=ModelJobResponse, tags=["models"])
def get_model_job(job_id: str, service: Service) -> ModelJobResponse:
    return ModelJobResponse.model_validate(service.get_model_job(job_id))


@router.post("/models/jobs/{job_id}/retry", response_model=ModelJobResponse, tags=["models"])
def retry_model_job(job_id: str, service: Service) -> ModelJobResponse:
    return ModelJobResponse.model_validate(service.retry_model_install(job_id))


@router.post("/models/jobs/{job_id}/cancel", response_model=ModelJobResponse, tags=["models"])
def cancel_model_job(job_id: str, service: Service) -> ModelJobResponse:
    return ModelJobResponse.model_validate(service.cancel_model_install(job_id))


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Report process liveness and the contract version."""

    return HealthResponse(version=__version__, api_version=API_VERSION)


@router.get("/version", response_model=VersionResponse, tags=["system"])
async def version() -> VersionResponse:
    """Return the desktop/Core compatibility handshake payload."""

    return VersionResponse(core_version=__version__, api_version=API_VERSION)


@router.post("/desktop/shutdown", status_code=status.HTTP_202_ACCEPTED, tags=["system"])
def desktop_shutdown(request: Request) -> None:
    shutdown = request.app.state.desktop_shutdown
    if shutdown is None:
        raise AppError(
            "desktop_shutdown_unavailable",
            "Desktop shutdown is not available for this Core process.",
            status_code=404,
        )
    shutdown()


@router.post(
    "/libraries",
    response_model=LibraryResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["libraries"],
)
def create_library(payload: LibraryCreate, service: Service) -> LibraryResponse:
    return LibraryResponse.model_validate(service.create_library(payload.name))


@router.get("/libraries", response_model=Page[LibraryResponse], tags=["libraries"])
def list_libraries(service: Service) -> Page[LibraryResponse]:
    items = [LibraryResponse.model_validate(item) for item in service.list_libraries()]
    return Page(items=items, page=PageInfo(limit=50))


@router.get("/libraries/{library_id}", response_model=LibraryResponse, tags=["libraries"])
def get_library(library_id: str, service: Service) -> LibraryResponse:
    return LibraryResponse.model_validate(service.get_library(library_id))


@router.patch("/libraries/{library_id}", response_model=LibraryResponse, tags=["libraries"])
def rename_library(library_id: str, payload: LibraryUpdate, service: Service) -> LibraryResponse:
    return LibraryResponse.model_validate(service.rename_library(library_id, payload.name))


@router.delete(
    "/libraries/{library_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["libraries"]
)
def delete_library(library_id: str, service: Service) -> Response:
    service.delete_library(library_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/libraries/{library_id}/sources",
    response_model=SourceImportResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["sources"],
)
def import_source(
    library_id: str,
    service: Service,
    file: Annotated[UploadFile, File()],
) -> SourceImportResponse:
    source, job, duplicate = service.import_source(
        library_id,
        file.filename or "document",
        file.content_type,
        file.file,
    )
    return SourceImportResponse(
        source=SourceResponse.model_validate(source),
        job=JobResponse.model_validate(job),
        duplicate=duplicate,
    )


@router.get(
    "/libraries/{library_id}/sources", response_model=Page[SourceResponse], tags=["sources"]
)
def list_sources(
    library_id: str,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
    filter_text: Annotated[str, Query(alias="filter", max_length=200)] = "",
    sort: Literal["updated-desc", "name-asc", "size-desc"] = "updated-desc",
) -> Page[SourceResponse]:
    normalized_filter = filter_text.strip().casefold()
    decoded = (
        decode_source_cursor(cursor, sort=sort, filter_text=normalized_filter) if cursor else None
    )
    records, has_more = service.list_sources_page(
        library_id,
        limit=limit,
        filter_text=normalized_filter,
        sort=sort,
        after_value=decoded.value if decoded else None,
        after_id=decoded.source_id if decoded else None,
    )
    next_cursor = None
    if has_more and records:
        last = records[-1]
        key: str | int
        if sort == "updated-desc":
            key = last.updated_at
        elif sort == "name-asc":
            key = last.name
        else:
            key = last.size_bytes
        next_cursor = encode_source_cursor(SourceCursor(sort, normalized_filter, key, last.id))
    items = [SourceResponse.model_validate(item) for item in records]
    return Page(items=items, page=PageInfo(limit=limit, next_cursor=next_cursor))


@router.get("/sources/{source_id}", response_model=SourceResponse, tags=["sources"])
def get_source(source_id: str, service: Service) -> SourceResponse:
    return SourceResponse.model_validate(service.get_source(source_id))


@router.get("/sources/{source_id}/content", response_model=SourceContentResponse, tags=["sources"])
def read_source(
    source_id: str,
    service: Service,
    start: Annotated[int, Query(ge=0)] = 0,
    end: Annotated[int | None, Query(ge=0)] = None,
) -> SourceContentResponse:
    return SourceContentResponse.model_validate(service.read_source(source_id, start, end))


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["sources"])
def delete_source(source_id: str, service: Service) -> Response:
    service.delete_source(source_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/libraries/{library_id}/search", response_model=SearchResponse, tags=["search"])
def search(library_id: str, payload: SearchRequest, service: Service) -> SearchResponse:
    results = service.search(
        library_id, payload.query, limit=payload.limit, lexical_only=payload.lexical_only
    )
    return SearchResponse(items=[SearchResultResponse.model_validate(result) for result in results])


@router.get("/jobs/{job_id}", response_model=JobResponse, tags=["jobs"])
def get_job(job_id: str, service: Service) -> JobResponse:
    return JobResponse.model_validate(service.get_job(job_id))


@router.post("/jobs/{job_id}/retry", response_model=JobResponse, tags=["jobs"])
def retry_job(job_id: str, service: Service) -> JobResponse:
    return JobResponse.model_validate(service.retry_job(job_id))
