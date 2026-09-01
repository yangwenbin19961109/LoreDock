"""Knowledge-library use cases used by HTTP and future MCP adapters."""

import hashlib
import json
import mimetypes
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path
from threading import RLock
from typing import BinaryIO
from uuid import uuid4

from loredock.application.errors import AppError
from loredock.application.records import JobRecord, LibraryRecord, SourceContent, SourceRecord
from loredock.ingestion import parse_path
from loredock.retrieval import (
    ChunkingConfig,
    HashingEmbeddingProvider,
    HybridSearchIndex,
    SearchResult,
)
from loredock.retrieval.chunking import chunk_document
from loredock.storage import AppDatabase, DataLayout
from loredock.storage.database import utc_timestamp

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".pdf", ".docx"}
MAX_SOURCE_BYTES = 100 * 1024 * 1024


class LoreDockService:
    def __init__(self, data_dir: Path) -> None:
        self.layout = DataLayout(data_dir)
        self.layout.initialize()
        self.database = AppDatabase(self.layout.root / "app.sqlite")
        self.database.recover_interrupted_jobs()
        self.provider = HashingEmbeddingProvider()
        self.chunking = ChunkingConfig()
        self._lock = RLock()

    def close(self) -> None:
        self.database.close()

    @staticmethod
    def _library(row: sqlite3.Row) -> LibraryRecord:
        return LibraryRecord(
            id=str(row["id"]),
            name=str(row["name"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _source(row: sqlite3.Row) -> SourceRecord:
        return SourceRecord(
            id=str(row["id"]),
            library_id=str(row["library_id"]),
            name=str(row["name"]),
            media_type=str(row["media_type"]),
            status=str(row["status"]),
            content_hash=str(row["content_hash"]),
            size_bytes=int(row["size_bytes"]),
            error=str(row["error"]) if row["error"] is not None else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _job(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=str(row["id"]),
            library_id=str(row["library_id"]),
            source_id=str(row["source_id"]) if row["source_id"] is not None else None,
            kind=str(row["kind"]),
            status=str(row["status"]),
            attempts=int(row["attempts"]),
            progress=float(row["progress"]),
            error=str(row["error"]) if row["error"] is not None else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def create_library(self, name: str) -> LibraryRecord:
        normalized = " ".join(name.split())
        if not normalized or len(normalized) > 120:
            raise AppError("invalid_library_name", "Library name must contain 1 to 120 characters.")
        library_id = str(uuid4())
        now = utc_timestamp()
        with self._lock:
            self.layout.create_library(library_id)
            try:
                with self.database.transaction() as connection:
                    connection.execute(
                        """
                        INSERT INTO libraries(id, name, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (library_id, normalized, now, now),
                    )
            except Exception:
                self.layout.delete_library(library_id)
                raise
        return LibraryRecord(library_id, normalized, now, now)

    def list_libraries(self) -> list[LibraryRecord]:
        with self._lock:
            rows = self.database.connection.execute(
                "SELECT * FROM libraries ORDER BY updated_at DESC, id"
            ).fetchall()
        return [self._library(row) for row in rows]

    def get_library(self, library_id: str) -> LibraryRecord:
        with self._lock:
            row = self.database.connection.execute(
                "SELECT * FROM libraries WHERE id = ?", (library_id,)
            ).fetchone()
        if row is None:
            raise AppError(
                "library_not_found", "The requested library does not exist.", status_code=404
            )
        return self._library(row)

    def rename_library(self, library_id: str, name: str) -> LibraryRecord:
        self.get_library(library_id)
        normalized = " ".join(name.split())
        if not normalized or len(normalized) > 120:
            raise AppError("invalid_library_name", "Library name must contain 1 to 120 characters.")
        now = utc_timestamp()
        with self._lock, self.database.transaction() as connection:
            connection.execute(
                "UPDATE libraries SET name = ?, updated_at = ? WHERE id = ?",
                (normalized, now, library_id),
            )
        return self.get_library(library_id)

    def delete_library(self, library_id: str) -> None:
        self.get_library(library_id)
        with self._lock:
            self.layout.delete_library(library_id)
            with self.database.transaction() as connection:
                connection.execute("DELETE FROM libraries WHERE id = ?", (library_id,))

    @staticmethod
    def _copy_and_hash(stream: BinaryIO, destination: Path) -> tuple[str, int]:
        temporary = destination.with_suffix(destination.suffix + ".part")
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("wb") as output:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
                    output.write(block)
                    size += len(block)
                    if size > MAX_SOURCE_BYTES:
                        raise AppError(
                            "source_too_large", "Documents larger than 100 MiB are not supported."
                        )
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return digest.hexdigest(), size

    def _set_job(
        self, job_id: str, status: str, progress: float, *, error: str | None = None
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE jobs SET status=?, progress=?, error=?, updated_at=? WHERE id=?
                """,
                (status, progress, error, utc_timestamp(), job_id),
            )

    def import_source(
        self, library_id: str, filename: str, media_type: str | None, stream: BinaryIO
    ) -> tuple[SourceRecord, JobRecord, bool]:
        self.get_library(library_id)
        safe_name = Path(filename.replace("\\", "/")).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise AppError(
                "unsupported_document", f"Unsupported document type: {suffix or '<none>'}"
            )
        source_id = str(uuid4())
        job_id = str(uuid4())
        raw_path = self.layout.source_raw_path(library_id, source_id, suffix)
        with self._lock:
            content_hash, size = self._copy_and_hash(stream, raw_path)
            duplicate = self.database.connection.execute(
                "SELECT * FROM sources WHERE library_id=? AND content_hash=?",
                (library_id, content_hash),
            ).fetchone()
            if duplicate is not None:
                raw_path.unlink(missing_ok=True)
                existing = self._source(duplicate)
                return existing, self.latest_job_for_source(existing.id), True
            now = utc_timestamp()
            resolved_media_type = (
                media_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
            )
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO sources(
                        id, library_id, name, media_type, suffix, status, content_hash,
                        size_bytes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        library_id,
                        safe_name,
                        resolved_media_type,
                        suffix,
                        content_hash,
                        size,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO jobs(
                        id, library_id, source_id, kind, status, attempts, progress,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, 'index_source', 'running', 1, 0.1, ?, ?)
                    """,
                    (job_id, library_id, source_id, now, now),
                )
            try:
                self._index_source(library_id, source_id, raw_path, job_id)
            except Exception as error:
                message = str(error)[:1000]
                with self.database.transaction() as connection:
                    connection.execute(
                        "UPDATE sources SET status='failed', error=?, updated_at=? WHERE id=?",
                        (message, utc_timestamp(), source_id),
                    )
                self._set_job(job_id, "failed", 1.0, error=message)
                raise AppError(
                    "source_index_failed", "The document could not be indexed."
                ) from error
            with self.database.transaction() as connection:
                connection.execute(
                    "UPDATE sources SET status='ready', updated_at=? WHERE id=?",
                    (utc_timestamp(), source_id),
                )
            self._set_job(job_id, "succeeded", 1.0)
        return self.get_source(source_id), self.get_job(job_id), False

    def _set_source_status(self, source_id: str, status: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE sources SET status=?, updated_at=? WHERE id=?",
                (status, utc_timestamp(), source_id),
            )

    def _index_source(self, library_id: str, source_id: str, raw_path: Path, job_id: str) -> None:
        paths = self.layout.library(library_id)
        self._set_source_status(source_id, "parsing")
        self._set_job(job_id, "running", 0.25)
        parsed = parse_path(raw_path, source_id=source_id, allowed_root=paths.raw)
        artifact_path = paths.artifacts / f"{source_id}.txt"
        artifact_path.write_text(parsed.text, encoding="utf-8")
        self._set_source_status(source_id, "chunking")
        self._set_job(job_id, "running", 0.5)
        chunks = chunk_document(parsed, self.chunking)
        self._set_source_status(source_id, "embedding")
        self._set_job(job_id, "running", 0.7)
        with HybridSearchIndex(paths.index, self.provider) as index:
            index.replace_source(source_id, chunks)
        manifest = {
            "schema_version": 2,
            "embedding": {
                "identifier": self.provider.identifier,
                "dimensions": self.provider.dimensions,
                "normalize": True,
            },
            "chunking": asdict(self.chunking),
        }
        temporary = paths.manifest.with_suffix(".json.part")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, paths.manifest)
        self._set_job(job_id, "running", 0.9)

    def list_sources(self, library_id: str) -> list[SourceRecord]:
        self.get_library(library_id)
        with self._lock:
            rows = self.database.connection.execute(
                "SELECT * FROM sources WHERE library_id=? ORDER BY created_at DESC, id",
                (library_id,),
            ).fetchall()
        return [self._source(row) for row in rows]

    def get_source(self, source_id: str) -> SourceRecord:
        with self._lock:
            row = self.database.connection.execute(
                "SELECT * FROM sources WHERE id=?", (source_id,)
            ).fetchone()
        if row is None:
            raise AppError(
                "source_not_found", "The requested source does not exist.", status_code=404
            )
        return self._source(row)

    def read_source(self, source_id: str, start: int = 0, end: int | None = None) -> SourceContent:
        source = self.get_source(source_id)
        artifact = self.layout.library(source.library_id).artifacts / f"{source_id}.txt"
        if not artifact.exists():
            raise AppError(
                "source_not_ready", "The source does not have a readable artifact.", status_code=409
            )
        text = artifact.read_text(encoding="utf-8")
        bounded_start = max(0, min(start, len(text)))
        bounded_end = min(end if end is not None else bounded_start + 8000, len(text))
        if bounded_end < bounded_start:
            raise AppError("invalid_range", "The requested character range is invalid.")
        return SourceContent(source_id, text[bounded_start:bounded_end], bounded_start, bounded_end)

    def delete_source(self, source_id: str) -> None:
        source = self.get_source(source_id)
        paths = self.layout.library(source.library_id)
        with self._lock:
            if paths.index.exists():
                with HybridSearchIndex(paths.index, self.provider) as index:
                    index.delete_source(source_id)
            (paths.artifacts / f"{source_id}.txt").unlink(missing_ok=True)
            self.layout.source_raw_path(
                source.library_id, source.id, Path(source.name).suffix
            ).unlink(missing_ok=True)
            with self.database.transaction() as connection:
                connection.execute("DELETE FROM sources WHERE id=?", (source_id,))

    def search(
        self, library_id: str, query: str, *, limit: int = 8, lexical_only: bool = False
    ) -> list[SearchResult]:
        self.get_library(library_id)
        normalized = query.strip()
        if not normalized:
            raise AppError("invalid_query", "Search query cannot be empty.")
        index_path = self.layout.library(library_id).index
        if not index_path.exists():
            return []
        with self._lock, HybridSearchIndex(index_path, self.provider) as index:
            return index.search(normalized, limit=limit, lexical_only=lexical_only)

    def get_job(self, job_id: str) -> JobRecord:
        with self._lock:
            row = self.database.connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
        if row is None:
            raise AppError("job_not_found", "The requested job does not exist.", status_code=404)
        return self._job(row)

    def retry_job(self, job_id: str) -> JobRecord:
        job = self.get_job(job_id)
        if job.status != "failed" or job.source_id is None:
            raise AppError(
                "job_not_retryable", "Only failed source jobs can be retried.", status_code=409
            )
        if job.attempts >= 3:
            raise AppError(
                "job_attempts_exhausted", "The job has reached its retry limit.", status_code=409
            )
        source = self.get_source(job.source_id)
        raw_path = self.layout.source_raw_path(
            source.library_id, source.id, Path(source.name).suffix.lower()
        )
        if not raw_path.exists():
            raise AppError(
                "source_file_missing", "The source file is no longer available.", status_code=409
            )
        with self._lock, self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE jobs SET status='running', attempts=attempts+1, progress=0.1,
                    error=NULL, updated_at=? WHERE id=?
                """,
                (utc_timestamp(), job_id),
            )
            connection.execute(
                "UPDATE sources SET status='pending', error=NULL, updated_at=? WHERE id=?",
                (utc_timestamp(), source.id),
            )
        try:
            self._index_source(source.library_id, source.id, raw_path, job_id)
        except Exception as error:
            message = str(error)[:1000]
            self._set_job(job_id, "failed", 1.0, error=message)
            raise AppError("source_index_failed", "The document could not be indexed.") from error
        with self._lock, self.database.transaction() as connection:
            connection.execute(
                "UPDATE sources SET status='ready', updated_at=? WHERE id=?",
                (utc_timestamp(), source.id),
            )
        self._set_job(job_id, "succeeded", 1.0)
        return self.get_job(job_id)

    def latest_job_for_source(self, source_id: str) -> JobRecord:
        row = self.database.connection.execute(
            "SELECT * FROM jobs WHERE source_id=? ORDER BY created_at DESC LIMIT 1", (source_id,)
        ).fetchone()
        if row is None:
            raise AppError(
                "job_not_found", "The source does not have an indexing job.", status_code=404
            )
        return self._job(row)
