"""Typed application-facing records independent from HTTP models."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class AppSettingsRecord:
    onboarding_completed: bool
    theme: Literal["system", "light", "dark"]
    default_search_mode: Literal["hybrid", "lexical"]
    updated_at: str


@dataclass(frozen=True, slots=True)
class ModelStatusRecord:
    model_id: str
    display_name: str
    state: Literal["missing", "ready", "corrupt"]
    active: bool
    restart_required: bool
    download_size_bytes: int
    required_space_bytes: int
    free_space_bytes: int
    error: str | None


@dataclass(frozen=True, slots=True)
class ModelJobRecord:
    id: str
    model_id: str
    status: Literal["pending", "running", "succeeded", "failed", "canceled"]
    attempts: int
    bytes_downloaded: int
    bytes_total: int
    current_file: str | None
    error: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class LibraryRecord:
    id: str
    name: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class SourceRecord:
    id: str
    library_id: str
    name: str
    media_type: str
    status: str
    content_hash: str
    size_bytes: int
    source_kind: Literal["file", "url"]
    origin_url: str | None
    error: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class JobRecord:
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


@dataclass(frozen=True, slots=True)
class SourceContent:
    source_id: str
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class IndexStatusRecord:
    library_id: str
    source_count: int
    ready_source_count: int
    failed_source_count: int
    pending_source_count: int
    index_present: bool
    embedding_model: str
    production_embeddings: bool
