"""Typed application-facing records independent from HTTP models."""

from dataclasses import dataclass


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
