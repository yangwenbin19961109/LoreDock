"""Versioned HTTP boundary models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    """Strict base class for public API contracts."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    service: Literal["loredock-core"] = "loredock-core"
    version: str
    api_version: str


class VersionResponse(ApiModel):
    product: Literal["LoreDock"] = "LoreDock"
    core_version: str
    api_version: str


class ErrorDetail(ApiModel):
    code: str
    message: str
    request_id: str | None = None
    fields: dict[str, list[str]] | None = None


class ErrorResponse(ApiModel):
    error: ErrorDetail


class PageInfo(ApiModel):
    limit: int = Field(ge=1, le=200)
    next_cursor: str | None = None


class Page[T](ApiModel):
    items: list[T]
    page: PageInfo


class LibraryCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)


class LibraryUpdate(ApiModel):
    name: str = Field(min_length=1, max_length=120)


class LibraryResponse(ApiModel):
    id: str
    name: str
    created_at: str
    updated_at: str


class SourceResponse(ApiModel):
    id: str
    library_id: str
    name: str
    media_type: str
    status: str
    content_hash: str
    size_bytes: int
    error: str | None
    created_at: str
    updated_at: str


class JobResponse(ApiModel):
    id: str
    library_id: str
    source_id: str | None
    kind: str
    status: str
    attempts: int
    progress: float
    error: str | None
    created_at: str
    updated_at: str


class SourceImportResponse(ApiModel):
    source: SourceResponse
    job: JobResponse
    duplicate: bool


class SearchRequest(ApiModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=8, ge=1, le=50)
    lexical_only: bool = False


class CitationRangeResponse(ApiModel):
    char_start: int
    char_end: int
    page_start: int | None
    page_end: int | None


class SearchResultResponse(ApiModel):
    chunk_id: str
    source_id: str
    text: str
    score: float
    char_start: int
    char_end: int
    page: int | None
    title_path: tuple[str, ...]
    matched_chunk_id: str
    parent_id: str | None
    context_id: str
    context_text: str
    matched_range: CitationRangeResponse
    context_range: CitationRangeResponse


class SearchResponse(ApiModel):
    items: list[SearchResultResponse]


class SourceContentResponse(ApiModel):
    source_id: str
    text: str
    char_start: int
    char_end: int
