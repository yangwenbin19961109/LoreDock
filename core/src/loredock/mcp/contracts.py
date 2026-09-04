"""Draft v1 MCP contracts with explicit response budgets."""

from pydantic import BaseModel, ConfigDict, Field


class ToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchKnowledgeRequest(ToolModel):
    library_id: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=8, ge=1, le=10)
    lexical_only: bool = False


class ReadSourceRequest(ToolModel):
    library_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    start: int = Field(default=0, ge=0)
    length: int = Field(default=4000, ge=1, le=8000)


class KnowledgeHit(ToolModel):
    library_id: str
    source_id: str
    source_name: str
    chunk_id: str
    parent_id: str | None
    text: str
    score: float
    char_start: int
    char_end: int
    matched_char_end: int
    page: int | None
    title_path: tuple[str, ...]
    truncated: bool
    read_reference: ReadSourceRequest


class KnowledgeResults(ToolModel):
    items: list[KnowledgeHit]


class SourceExcerpt(ToolModel):
    library_id: str
    source_id: str
    text: str
    char_start: int
    char_end: int
    next_start: int | None


class ListLibrariesRequest(ToolModel):
    after_id: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=20, ge=1, le=50)


class LibrarySummary(ToolModel):
    id: str
    name: str


class LibraryList(ToolModel):
    items: list[LibrarySummary]
    next_after_id: str | None


class LibraryRequest(ToolModel):
    library_id: str = Field(min_length=1, max_length=128)


class SourceInfoRequest(LibraryRequest):
    source_id: str = Field(min_length=1, max_length=128)


class ListSourcesRequest(LibraryRequest):
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, min_length=1, max_length=2000)


class SourceSummary(ToolModel):
    id: str
    library_id: str
    name: str
    media_type: str
    status: str
    size_bytes: int
    created_at: str
    updated_at: str


class SourceList(ToolModel):
    items: list[SourceSummary]
    next_cursor: str | None


class IndexStatus(ToolModel):
    library_id: str
    source_count: int
    ready_source_count: int
    failed_source_count: int
    pending_source_count: int
    index_present: bool
    embedding_model: str
    production_embeddings: bool
