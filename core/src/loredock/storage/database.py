"""SQLite metadata store with deterministic, retry-safe migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCHEMA_VERSION = 4


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


class AppDatabase:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.migrate()

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
                SET status='failed', error='Core stopped while the job was running', updated_at=?
                WHERE status='running'
                """,
                (now,),
            )
            self.connection.execute(
                """
                UPDATE sources SET status='failed', error='Indexing was interrupted', updated_at=?
                WHERE status IN ('pending', 'parsing', 'chunking', 'embedding')
                """,
                (now,),
            )
        return cursor.rowcount

    def lease_next_job(self, worker_id: str, *, lease_seconds: int = 60) -> sqlite3.Row | None:
        now = datetime.now(UTC)
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self.connection:
            row = self.connection.execute(
                """
                SELECT * FROM jobs
                WHERE status='pending' AND attempts < 3
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
