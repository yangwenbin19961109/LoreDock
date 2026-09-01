"""Versioned HTTP adapter for LoreDock application use cases."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status

from loredock.api.contracts import (
    HealthResponse,
    JobResponse,
    LibraryCreate,
    LibraryResponse,
    LibraryUpdate,
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
from loredock.application import LoreDockService
from loredock.version import API_VERSION, __version__

router = APIRouter(prefix=f"/api/{API_VERSION}")


def get_service(request: Request) -> LoreDockService:
    return request.app.state.service


Service = Annotated[LoreDockService, Depends(get_service)]


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Report process liveness and the contract version."""

    return HealthResponse(version=__version__, api_version=API_VERSION)


@router.get("/version", response_model=VersionResponse, tags=["system"])
async def version() -> VersionResponse:
    """Return the desktop/Core compatibility handshake payload."""

    return VersionResponse(core_version=__version__, api_version=API_VERSION)


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
def list_sources(library_id: str, service: Service) -> Page[SourceResponse]:
    items = [SourceResponse.model_validate(item) for item in service.list_sources(library_id)]
    return Page(items=items, page=PageInfo(limit=50))


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
