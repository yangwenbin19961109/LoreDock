"""SQLite metadata store with deterministic, retry-safe migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock

from loredock.version import APP_SCHEMA_VERSION

SCHEMA_VERSION = APP_SCHEMA_VERSION
_timestamp_lock = Lock()
_last_timestamp: datetime | None = None


def utc_timestamp() -> str:
    global _last_timestamp
    with _timestamp_lock:
        current = datetime.now(UTC)
        if _last_timestamp is not None and current <= _last_timestamp:
            current = _last_timestamp + timedelta(microseconds=1)
        _last_timestamp = current
        return current.isoformat()


class AppDatabase:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        try:
            self.migrate()
            self.connection.execute("PRAGMA journal_mode=WAL")
        except Exception:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        with self.connection:
            yield self.connection

    def migrate(self) -> None:
        version = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            raise RuntimeError("app.sqlite was created by a newer LoreDock version")
        if version < 1:
            with self.connection:
                self.connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS libraries (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS sources (
                        id TEXT PRIMARY KEY,
                        library_id TEXT NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        media_type TEXT NOT NULL,
                        suffix TEXT NOT NULL,
                        status TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        error TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(library_id, content_hash)
                    );
                    CREATE INDEX IF NOT EXISTS sources_library_id
                    ON sources(library_id, created_at);
                    CREATE TABLE IF NOT EXISTS jobs (
                        id TEXT PRIMARY KEY,
                        library_id TEXT NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
                        source_id TEXT REFERENCES sources(id) ON DELETE CASCADE,
                        kind TEXT NOT NULL,
                        status TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        progress REAL NOT NULL DEFAULT 0,
                        lease_until TEXT,
                        error TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created_at);
                    PRAGMA user_version=1;
                    """
                )
        if version < 2:
            with self.connection:
                self.connection.execute("ALTER TABLE jobs ADD COLUMN lease_owner TEXT")
                self.connection.execute("PRAGMA user_version=2")
        if version < 3:
            with self.connection:
                self.connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS app_settings (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        onboarding_completed INTEGER NOT NULL DEFAULT 0,
                        theme TEXT NOT NULL DEFAULT 'system'
                            CHECK (theme IN ('system', 'light', 'dark')),
                        default_search_mode TEXT NOT NULL DEFAULT 'hybrid'
                            CHECK (default_search_mode IN ('hybrid', 'lexical')),
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                self.connection.execute(
                    "INSERT OR IGNORE INTO app_settings(id, updated_at) VALUES (1, ?)",
                    (utc_timestamp(),),
                )
                self.connection.execute("PRAGMA user_version=3")
        if version < 4:
            with self.connection:
                self.connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS model_jobs (
                        id TEXT PRIMARY KEY,
                        model_id TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (
                            status IN ('pending', 'running', 'succeeded', 'failed', 'canceled')
                        ),
                        attempts INTEGER NOT NULL DEFAULT 0,
                        bytes_downloaded INTEGER NOT NULL DEFAULT 0,
                        bytes_total INTEGER NOT NULL,
                        current_file TEXT,
                        error TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS model_jobs_status
                    ON model_jobs(status, created_at);
                    PRAGMA user_version=4;
                    """
                )

        if version < 5:
            with self.connection:
                self.connection.execute(
                    "CREATE TABLE IF NOT EXISTS source_activity ("
                    "source_id TEXT PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE, "
                    "last_opened TEXT, favorite_at TEXT)"
                )
                self.connection.execute(
                    "CREATE INDEX IF NOT EXISTS activity_recent "
                    "ON source_activity(last_opened DESC, source_id)"
                )
                self.connection.execute(
                    "CREATE INDEX IF NOT EXISTS activity_favorites "
                    "ON source_activity(favorite_at DESC, source_id)"
                )
                self.connection.execute("PRAGMA user_version=5")

        if version < 6:
            with self.connection:
                source_columns = {
                    str(row[1]) for row in self.connection.execute("PRAGMA table_info(sources)")
                }
                if "source_kind" not in source_columns:
                    self.connection.execute(
                        "ALTER TABLE sources ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'file' "
                        "CHECK (source_kind IN ('file', 'url'))"
                    )
                if "origin_url" not in source_columns:
                    self.connection.execute("ALTER TABLE sources ADD COLUMN origin_url TEXT")
                self.connection.execute("PRAGMA user_version=6")

        if version < 7:
            with self.connection:
                self.connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS import_batches (
                        id TEXT PRIMARY KEY,
                        library_id TEXT NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        expected_items INTEGER NOT NULL CHECK (expected_items >= 1),
                        sealed INTEGER NOT NULL DEFAULT 0 CHECK (sealed IN (0, 1)),
                        control_state TEXT NOT NULL DEFAULT 'active'
                            CHECK (control_state IN ('active', 'paused', 'canceled')),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS import_batches_library
                    ON import_batches(library_id, created_at DESC, id DESC);
                    CREATE TABLE IF NOT EXISTS import_batch_items (
                        id TEXT PRIMARY KEY,
                        batch_id TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
                        source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
                        job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
                        name TEXT NOT NULL,
                        outcome TEXT NOT NULL CHECK (outcome IN ('queued', 'duplicate')),
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS import_batch_items_batch
                    ON import_batch_items(batch_id, created_at, id);
                    """
                )
                jobs_exist = self.connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'"
                ).fetchone()
                if jobs_exist is not None:
                    job_columns = {
                        str(row[1]) for row in self.connection.execute("PRAGMA table_info(jobs)")
                    }
                    if "batch_id" not in job_columns:
                        self.connection.execute(
                            "ALTER TABLE jobs ADD COLUMN batch_id TEXT "
                            "REFERENCES import_batches(id) ON DELETE SET NULL"
                        )
                    self.connection.execute(
                        "CREATE INDEX IF NOT EXISTS jobs_batch_id ON jobs(batch_id, created_at, id)"
                    )
                self.connection.execute("PRAGMA user_version=7")

    def recover_model_jobs(self) -> int:
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE model_jobs SET status='pending', updated_at=?
                WHERE status='running'
                """,
                (utc_timestamp(),),
            )
        return cursor.rowcount

    def recover_interrupted_jobs(self) -> int:
        now = utc_timestamp()
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE jobs
                SET status='pending', progress=0.1, lease_owner=NULL, lease_until=NULL,
                    error=NULL, updated_at=?
                WHERE status='running' AND attempts < 3
                """,
                (now,),
            )
            recovered = cursor.rowcount
            exhausted = self.connection.execute(
                """
                UPDATE jobs SET status='failed', progress=1, lease_owner=NULL, lease_until=NULL,
                    error='Indexing was interrupted after the retry limit', updated_at=?
                WHERE status='running' AND attempts >= 3
                """,
                (now,),
            ).rowcount
            self.connection.execute(
                """
                UPDATE sources SET status='pending', error=NULL, updated_at=?
                WHERE id IN (SELECT source_id FROM jobs WHERE status='pending')
                """,
                (now,),
            )
            self.connection.execute(
                """
                UPDATE sources SET status='failed',
                    error='Indexing was interrupted after the retry limit', updated_at=?
                WHERE id IN (
                    SELECT source_id FROM jobs
                    WHERE status='failed' AND error='Indexing was interrupted after the retry limit'
                )
                """,
                (now,),
            )
        return recovered + exhausted

    def lease_next_job(self, worker_id: str, *, lease_seconds: int = 60) -> sqlite3.Row | None:
        now = datetime.now(UTC)
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self.connection:
            row = self.connection.execute(
                """
                SELECT * FROM jobs
                WHERE status='pending' AND attempts < 3
                  AND (batch_id IS NULL OR EXISTS (
                      SELECT 1 FROM import_batches b
                      WHERE b.id=jobs.batch_id AND b.control_state='active'
                  ))
                ORDER BY created_at, id LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            self.connection.execute(
                """
                UPDATE jobs
                SET status='running', attempts=attempts+1,
                    lease_owner=?, lease_until=?, updated_at=?
                WHERE id=? AND status='pending'
                """,
                (worker_id, lease_until, now.isoformat(), str(row["id"])),
            )
            return self.connection.execute(
                "SELECT * FROM jobs WHERE id=?", (str(row["id"]),)
            ).fetchone()

    def heartbeat(self, job_id: str, worker_id: str, *, lease_seconds: int = 60) -> bool:
        lease_until = (datetime.now(UTC) + timedelta(seconds=lease_seconds)).isoformat()
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE jobs SET lease_until=?, updated_at=?
                WHERE id=? AND status='running' AND lease_owner=?
                """,
                (lease_until, utc_timestamp(), job_id, worker_id),
            )
        return cursor.rowcount == 1

    def backup(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup_connection = sqlite3.connect(destination)
        try:
            with backup_connection:
                self.connection.backup(backup_connection)
        finally:
            backup_connection.close()
