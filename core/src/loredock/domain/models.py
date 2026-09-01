"""Initial framework-independent domain vocabulary for Phase 0."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import NewType
from uuid import UUID, uuid4

LibraryId = NewType("LibraryId", UUID)
SourceId = NewType("SourceId", UUID)
ArtifactId = NewType("ArtifactId", UUID)
ChunkId = NewType("ChunkId", UUID)
JobId = NewType("JobId", UUID)


def utc_now() -> datetime:
    """Return an aware UTC timestamp for domain defaults."""

    return datetime.now(UTC)


class SourceKind(StrEnum):
    FILE = "file"
    URL = "url"
    NOTE = "note"


class SourceStatus(StrEnum):
    PENDING = "pending"
    SNAPSHOTTING = "snapshotting"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Library:
    name: str
    id: LibraryId = field(default_factory=lambda: LibraryId(uuid4()))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class Source:
    library_id: LibraryId
    name: str
    kind: SourceKind
    status: SourceStatus = SourceStatus.PENDING
    id: SourceId = field(default_factory=lambda: SourceId(uuid4()))
    content_hash: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class Artifact:
    source_id: SourceId
    relative_path: str
    media_type: str
    id: ArtifactId = field(default_factory=lambda: ArtifactId(uuid4()))


@dataclass(frozen=True, slots=True)
class Chunk:
    source_id: SourceId
    text: str
    content_hash: str
    char_start: int
    char_end: int
    id: ChunkId = field(default_factory=lambda: ChunkId(uuid4()))
    page: int | None = None
    title_path: tuple[str, ...] = ()
    previous_id: ChunkId | None = None
    next_id: ChunkId | None = None


@dataclass(frozen=True, slots=True)
class Job:
    kind: str
    status: JobStatus = JobStatus.PENDING
    id: JobId = field(default_factory=lambda: JobId(uuid4()))
    attempts: int = 0
    progress: float = 0.0
    error: str | None = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ModelProfile:
    identifier: str
    checksum: str
    dimensions: int
    distance: str = "cosine"
    normalize: bool = True
    query_prefix: str = "query: "
    document_prefix: str = "passage: "
    chunker_version: int = 1
    index_schema_version: int = 1
