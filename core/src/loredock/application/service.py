"""Knowledge-library use cases used by HTTP and future MCP adapters."""

import hashlib
import json
import mimetypes
import os
import shutil
import sqlite3
from dataclasses import asdict
from pathlib import Path
from threading import Event, RLock, Thread
from typing import BinaryIO
from uuid import uuid4

from loredock.application.errors import AppError
from loredock.application.records import (
    AppSettingsRecord,
    IndexStatusRecord,
    JobRecord,
    LibraryRecord,
    ModelJobRecord,
    ModelStatusRecord,
    SourceContent,
    SourceRecord,
)
from loredock.ingestion import parse_path
from loredock.retrieval import (
    ChunkingConfig,
    EmbeddingProvider,
    HashingEmbeddingProvider,
    HybridSearchIndex,
    SearchResult,
    chunk_document_hierarchy,
)
from loredock.retrieval.model_assets import (
    E5_ASSETS,
    E5_MODEL_ID,
    ModelDownloadCancelled,
    install_e5_package,
    required_e5_install_bytes,
    validate_e5_package,
)
from loredock.storage import AppDatabase, DataLayout
from loredock.storage.database import utc_timestamp

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".pdf", ".docx"}
MAX_SOURCE_BYTES = 100 * 1024 * 1024


class LoreDockService:
    def __init__(self, data_dir: Path, provider: EmbeddingProvider | None = None) -> None:
        self.layout = DataLayout(data_dir)
        self.layout.initialize()
        self.database = AppDatabase(self.layout.root / "app.sqlite")
        self.database.recover_interrupted_jobs()
        self.provider = provider or HashingEmbeddingProvider()
        self.chunking = ChunkingConfig()
        self._lock = RLock()
        self._model_stop = Event()
        self._model_cancel = Event()
        self._model_thread: Thread | None = None
        self.database.recover_model_jobs()
        pending = self.database.connection.execute(
            "SELECT id FROM model_jobs WHERE status='pending' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if pending is not None:
            self._start_model_worker(str(pending["id"]))

    @property
    def managed_model_dir(self) -> Path:
        return self.layout.root / "models" / "multilingual-e5-small"

    def get_default_model_status(self) -> ModelStatusRecord:
        state = "missing"
        error = None
        if self.managed_model_dir.exists():
            try:
                validate_e5_package(self.managed_model_dir)
                state = "ready"
            except ValueError as reason:
                state = "corrupt"
                error = str(reason)
        active = self.provider.identifier.startswith(E5_MODEL_ID)
        return ModelStatusRecord(
            model_id=E5_MODEL_ID,
            display_name="多语言快速模型",
            state=state,
            active=active,
            restart_required=state == "ready" and not active,
            download_size_bytes=sum(asset.size_bytes for asset in E5_ASSETS),
            required_space_bytes=required_e5_install_bytes(),
            free_space_bytes=shutil.disk_usage(self.layout.root).free,
            error=error,
        )

    @staticmethod
    def _model_job(row: sqlite3.Row) -> ModelJobRecord:
        return ModelJobRecord(
            id=str(row["id"]),
            model_id=str(row["model_id"]),
            status=row["status"],
            attempts=int(row["attempts"]),
            bytes_downloaded=int(row["bytes_downloaded"]),
            bytes_total=int(row["bytes_total"]),
            current_file=str(row["current_file"]) if row["current_file"] else None,
            error=str(row["error"]) if row["error"] else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def get_model_job(self, job_id: str) -> ModelJobRecord:
        with self._lock:
            row = self.database.connection.execute(
                "SELECT * FROM model_jobs WHERE id=?", (job_id,)
            ).fetchone()
        if row is None:
            raise AppError("model_job_not_found", "The model job does not exist.", status_code=404)
        return self._model_job(row)

    def latest_model_job(self) -> ModelJobRecord | None:
        with self._lock:
            row = self.database.connection.execute(
                "SELECT * FROM model_jobs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return self._model_job(row) if row is not None else None

    def start_model_install(self) -> ModelJobRecord:
        existing = self.latest_model_job()
        if existing is not None and existing.status in {"pending", "running"}:
            return existing
        job_id = str(uuid4())
        now = utc_timestamp()
        with self._lock, self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO model_jobs(
                    id, model_id, status, bytes_total, created_at, updated_at
                ) VALUES (?, ?, 'pending', ?, ?, ?)
                """,
                (job_id, E5_MODEL_ID, sum(asset.size_bytes for asset in E5_ASSETS), now, now),
            )
        self._start_model_worker(job_id)
        return self.get_model_job(job_id)

    def retry_model_install(self, job_id: str) -> ModelJobRecord:
        job = self.get_model_job(job_id)
        if job.status not in {"failed", "canceled"}:
            raise AppError(
                "model_job_not_retryable", "The model job cannot be retried.", status_code=409
            )
        with self._lock, self.database.transaction() as connection:
            connection.execute(
                "UPDATE model_jobs SET status='pending', error=NULL, updated_at=? WHERE id=?",
                (utc_timestamp(), job_id),
            )
        self._start_model_worker(job_id)
        return self.get_model_job(job_id)

    def cancel_model_install(self, job_id: str) -> ModelJobRecord:
        job = self.get_model_job(job_id)
        if job.status not in {"pending", "running"}:
            raise AppError(
                "model_job_not_cancelable", "The model job cannot be canceled.", status_code=409
            )
        self._model_cancel.set()
        if self._model_thread is not None:
            self._model_thread.join(timeout=0.5)
        return self.get_model_job(job_id)

    def _start_model_worker(self, job_id: str) -> None:
        if self._model_thread is not None and self._model_thread.is_alive():
            return
        self._model_cancel.clear()
        self._model_thread = Thread(
            target=self._run_model_install,
            args=(job_id,),
            name="loredock-model-installer",
            daemon=True,
        )
        self._model_thread.start()

    def _run_model_install(self, job_id: str) -> None:
        with self._lock, self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE model_jobs SET status='running', attempts=attempts+1,
                    error=NULL, updated_at=? WHERE id=? AND status='pending'
                """,
                (utc_timestamp(), job_id),
            )

        def update_progress(downloaded: int, total: int, filename: str) -> None:
            with self._lock, self.database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE model_jobs SET bytes_downloaded=?, bytes_total=?, current_file=?,
                        updated_at=? WHERE id=? AND status='running'
                    """,
                    (downloaded, total, filename, utc_timestamp(), job_id),
                )

        try:
            install_e5_package(
                self.managed_model_dir,
                progress=update_progress,
                should_cancel=lambda: self._model_cancel.is_set() or self._model_stop.is_set(),
            )
        except ModelDownloadCancelled:
            status = "pending" if self._model_stop.is_set() else "canceled"
            with self._lock, self.database.transaction() as connection:
                connection.execute(
                    "UPDATE model_jobs SET status=?, updated_at=? WHERE id=?",
                    (status, utc_timestamp(), job_id),
                )
        except Exception as reason:
            with self._lock, self.database.transaction() as connection:
                connection.execute(
                    "UPDATE model_jobs SET status='failed', error=?, updated_at=? WHERE id=?",
                    (str(reason)[:1000], utc_timestamp(), job_id),
                )
        else:
            with self._lock, self.database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE model_jobs SET status='succeeded', bytes_downloaded=bytes_total,
                        current_file=NULL, updated_at=? WHERE id=?
                    """,
                    (utc_timestamp(), job_id),
                )

    def get_settings(self) -> AppSettingsRecord:
        row = self.database.connection.execute("SELECT * FROM app_settings WHERE id=1").fetchone()
        if row is None:
            raise RuntimeError("app settings row is missing")
        return AppSettingsRecord(
            onboarding_completed=bool(row["onboarding_completed"]),
            theme=row["theme"],
            default_search_mode=row["default_search_mode"],
            updated_at=str(row["updated_at"]),
        )

    def update_settings(
        self,
        *,
        onboarding_completed: bool,
        theme: str,
        default_search_mode: str,
    ) -> AppSettingsRecord:
        if theme not in {"system", "light", "dark"}:
            raise AppError("invalid_theme", "The requested theme is invalid.")
        if default_search_mode not in {"hybrid", "lexical"}:
            raise AppError("invalid_search_mode", "The requested search mode is invalid.")
        with self._lock, self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE app_settings
                SET onboarding_completed=?, theme=?, default_search_mode=?, updated_at=?
                WHERE id=1
                """,
                (onboarding_completed, theme, default_search_mode, utc_timestamp()),
            )
        return self.get_settings()

    def _manifest_payload(self) -> dict[str, object]:
        return {
            "schema_version": 3,
            "embedding": {
                "identifier": self.provider.identifier,
                "dimensions": self.provider.dimensions,
                "normalize": True,
            },
            "chunking": asdict(self.chunking),
            "hierarchy": {
                "version": 1,
                "ranking_unit": "child",
                "context_strategy": "bounded_parent_or_range",
            },
        }

    def _write_manifest(self, library_id: str) -> None:
        manifest = self.layout.library(library_id).manifest
        temporary = manifest.with_suffix(".json.part")
        temporary.write_text(
            json.dumps(self._manifest_payload(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, manifest)

    def _ensure_index_contract(self, library_id: str) -> None:
        paths = self.layout.library(library_id)
        if not paths.index.exists():
            return
        expected_metadata = {
            "schema_version": "3",
            "embedding_provider": self.provider.identifier,
            "embedding_dimensions": str(self.provider.dimensions),
            "embedding_normalized": "true",
        }
        actual_metadata: dict[str, str] = {}
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(paths.index)
            actual_metadata = {
                str(key): str(value)
                for key, value in connection.execute("SELECT key, value FROM index_metadata")
            }
        except sqlite3.Error:
            actual_metadata = {}
        finally:
            if connection is not None:
                connection.close()
        schema_version = None
        if paths.manifest.exists():
            try:
                schema_version = json.loads(paths.manifest.read_text(encoding="utf-8")).get(
                    "schema_version"
                )
            except (OSError, json.JSONDecodeError):
                schema_version = None
        if schema_version == 3 and actual_metadata == expected_metadata:
            return
        self._rebuild_library_index(library_id)

    def _rebuild_library_index(self, library_id: str) -> None:
        """Rebuild derived v3 data beside the active index, then switch atomically."""

        paths = self.layout.library(library_id)
        temporary = paths.index.with_name(f"{paths.index.name}.rebuild")
        for candidate in (
            temporary,
            Path(f"{temporary}-wal"),
            Path(f"{temporary}-shm"),
        ):
            candidate.unlink(missing_ok=True)
        rows = self.database.connection.execute(
            "SELECT id, suffix FROM sources WHERE library_id=? AND status='ready' ORDER BY id",
            (library_id,),
        ).fetchall()
        try:
            with HybridSearchIndex(temporary, self.provider) as index:
                for row in rows:
                    source_id = str(row["id"])
                    raw_path = self.layout.source_raw_path(
                        library_id, source_id, str(row["suffix"])
                    )
                    parsed = parse_path(raw_path, source_id=source_id, allowed_root=paths.raw)
                    hierarchy = chunk_document_hierarchy(parsed, self.chunking)
                    index.replace_source(source_id, hierarchy.chunks, hierarchy.parents)
            for sidecar in (Path(f"{paths.index}-wal"), Path(f"{paths.index}-shm")):
                sidecar.unlink(missing_ok=True)
            os.replace(temporary, paths.index)
            self._write_manifest(library_id)
        except Exception:
            for candidate in (
                temporary,
                Path(f"{temporary}-wal"),
                Path(f"{temporary}-shm"),
            ):
                candidate.unlink(missing_ok=True)
            raise

    def close(self) -> None:
        self._model_stop.set()
        if self._model_thread is not None:
            self._model_thread.join(timeout=2)
        if self._model_thread is not None and self._model_thread.is_alive():
            return
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
        with self._lock:
            self._ensure_index_contract(library_id)
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
        hierarchy = chunk_document_hierarchy(parsed, self.chunking)
        self._set_source_status(source_id, "embedding")
        self._set_job(job_id, "running", 0.7)
        with HybridSearchIndex(paths.index, self.provider) as index:
            index.replace_source(source_id, hierarchy.chunks, hierarchy.parents)
        self._write_manifest(library_id)
        self._set_job(job_id, "running", 0.9)

    def list_sources(self, library_id: str) -> list[SourceRecord]:
        self.get_library(library_id)
        with self._lock:
            rows = self.database.connection.execute(
                "SELECT * FROM sources WHERE library_id=? ORDER BY created_at DESC, id",
                (library_id,),
            ).fetchall()
        return [self._source(row) for row in rows]

    def list_sources_page(
        self,
        library_id: str,
        *,
        limit: int,
        filter_text: str = "",
        sort: str = "updated-desc",
        after_value: str | int | None = None,
        after_id: str | None = None,
    ) -> tuple[list[SourceRecord], bool]:
        """Return a stable keyset page and whether another page is available."""

        self.get_library(library_id)
        clauses = ["library_id=?"]
        parameters: list[object] = [library_id]
        normalized_filter = filter_text.strip().casefold()
        if normalized_filter:
            escaped = (
                normalized_filter.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            clauses.append(
                "(lower(name) LIKE ? ESCAPE '\\' OR lower(media_type) LIKE ? ESCAPE '\\' "
                "OR lower(status) LIKE ? ESCAPE '\\')"
            )
            pattern = f"%{escaped}%"
            parameters.extend([pattern, pattern, pattern])

        order_by: str
        if sort == "updated-desc":
            order_by = "updated_at DESC, id ASC"
            if after_value is not None and after_id is not None:
                clauses.append("(updated_at < ? OR (updated_at = ? AND id > ?))")
                parameters.extend([after_value, after_value, after_id])
        elif sort == "name-asc":
            order_by = "name COLLATE NOCASE ASC, id ASC"
            if after_value is not None and after_id is not None:
                clauses.append("(name COLLATE NOCASE > ? OR (name COLLATE NOCASE = ? AND id > ?))")
                parameters.extend([after_value, after_value, after_id])
        elif sort == "size-desc":
            order_by = "size_bytes DESC, id ASC"
            if after_value is not None and after_id is not None:
                clauses.append("(size_bytes < ? OR (size_bytes = ? AND id > ?))")
                parameters.extend([after_value, after_value, after_id])
        else:
            raise AppError("invalid_source_sort", "The requested source sort is invalid.")

        parameters.append(limit + 1)
        statement = (
            f"SELECT * FROM sources WHERE {' AND '.join(clauses)} ORDER BY {order_by} LIMIT ?"
        )
        with self._lock:
            rows = self.database.connection.execute(statement, parameters).fetchall()
        has_more = len(rows) > limit
        return [self._source(row) for row in rows[:limit]], has_more

    def get_index_status(self, library_id: str) -> IndexStatusRecord:
        """Return metadata status, not a claim of index integrity or model quality."""
        self.get_library(library_id)
        with self._lock:
            rows = self.database.connection.execute(
                "SELECT status, COUNT(*) AS count FROM sources WHERE library_id=? GROUP BY status",
                (library_id,),
            ).fetchall()
            counts = {str(row["status"]): int(row["count"]) for row in rows}
            total = sum(counts.values())
            ready = counts.get("ready", 0)
            failed = counts.get("failed", 0)
            return IndexStatusRecord(
                library_id=library_id,
                source_count=total,
                ready_source_count=ready,
                failed_source_count=failed,
                pending_source_count=total - ready - failed,
                index_present=self.layout.library(library_id).index.is_file(),
                embedding_model=self.provider.identifier,
                production_embeddings=not isinstance(self.provider, HashingEmbeddingProvider),
            )

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

    def source_is_favorite(self, source_id: str) -> bool:
        with self._lock:
            self.get_source(source_id)
            row = self.database.connection.execute(
                "SELECT favorite_at FROM source_activity WHERE source_id=?", (source_id,)
            ).fetchone()
            return row is not None and row["favorite_at"] is not None

    def set_source_favorite(self, source_id: str, favorite: bool) -> bool:
        with self._lock, self.database.transaction() as db:
            self.get_source(source_id)
            if favorite:
                # Repeated PUT does not reorder an existing favorite.
                db.execute(
                    "INSERT INTO source_activity(source_id, favorite_at) VALUES (?, ?) "
                    "ON CONFLICT(source_id) DO UPDATE SET "
                    "favorite_at=COALESCE(source_activity.favorite_at, excluded.favorite_at)",
                    (source_id, utc_timestamp()),
                )
            else:
                db.execute(
                    "UPDATE source_activity SET favorite_at=NULL WHERE source_id=?", (source_id,)
                )
                db.execute(
                    "DELETE FROM source_activity WHERE source_id=? AND last_opened IS NULL",
                    (source_id,),
                )
        return favorite

    def record_source_visit(self, source_id: str) -> None:
        with self._lock, self.database.transaction() as db:
            self.get_source(source_id)
            db.execute(
                "INSERT INTO source_activity(source_id, last_opened) VALUES (?, ?) "
                "ON CONFLICT(source_id) DO UPDATE SET last_opened=excluded.last_opened",
                (source_id, utc_timestamp()),
            )
            # Bound recent history independently; pruning history never removes favorites.
            db.execute(
                "UPDATE source_activity SET last_opened=NULL WHERE source_id IN ("
                "SELECT source_id FROM source_activity WHERE last_opened IS NOT NULL "
                "ORDER BY last_opened DESC, source_id LIMIT -1 OFFSET 100)"
            )
            db.execute(
                "DELETE FROM source_activity WHERE last_opened IS NULL AND favorite_at IS NULL"
            )

    def list_source_collection(
        self, kind: str, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[SourceRecord], bool]:
        if kind not in ("recent", "favorites") or not 1 <= limit <= 50 or offset < 0:
            raise AppError("invalid_collection", "Collection parameters are invalid.")
        column = "last_opened" if kind == "recent" else "favorite_at"
        with self._lock:
            rows = self.database.connection.execute(
                f"SELECT s.* FROM source_activity a JOIN sources s ON s.id=a.source_id "
                f"WHERE a.{column} IS NOT NULL ORDER BY a.{column} DESC, a.source_id "
                "LIMIT ? OFFSET ?",
                (limit + 1, offset),
            ).fetchall()
        return [self._source(row) for row in rows[:limit]], len(rows) > limit

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
            self._ensure_index_contract(source.library_id)
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
        with self._lock:
            self._ensure_index_contract(library_id)
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
