import sqlite3
from pathlib import Path

from loredock.storage import AppDatabase, DataLayout
from loredock.storage.database import utc_timestamp
from loredock.version import APP_SCHEMA_VERSION


def test_migration_is_retry_safe(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite"
    first = AppDatabase(path)
    first.close()
    second = AppDatabase(path)

    version = second.connection.execute("PRAGMA user_version").fetchone()[0]
    second.close()

    assert version == 7


def test_newer_schema_is_rejected_without_changing_its_version(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite"
    connection = sqlite3.connect(path)
    connection.execute(f"PRAGMA user_version={APP_SCHEMA_VERSION + 1}")
    connection.close()

    try:
        AppDatabase(path)
    except RuntimeError as error:
        assert "newer LoreDock version" in str(error)
    else:
        raise AssertionError("Expected a newer schema to be rejected")

    connection = sqlite3.connect(path)
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    connection.close()
    assert version == APP_SCHEMA_VERSION + 1
    assert journal_mode == "delete"


def test_settings_migration_has_safe_defaults(tmp_path: Path) -> None:
    database = AppDatabase(tmp_path / "app.sqlite")
    row = database.connection.execute("SELECT * FROM app_settings WHERE id=1").fetchone()
    database.close()

    assert row is not None
    assert row["onboarding_completed"] == 0
    assert row["theme"] == "system"
    assert row["default_search_mode"] == "hybrid"


def test_schema_two_migrates_to_settings_without_reset(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite"
    fixture = AppDatabase(path)
    fixture.connection.execute("DROP TABLE source_activity")
    fixture.connection.execute("DROP TABLE model_jobs")
    fixture.connection.execute("DROP TABLE app_settings")
    fixture.connection.execute("PRAGMA user_version=2")
    fixture.connection.commit()
    fixture.close()

    database = AppDatabase(path)
    version = database.connection.execute("PRAGMA user_version").fetchone()[0]
    settings = database.connection.execute("SELECT theme FROM app_settings WHERE id=1").fetchone()
    database.close()

    assert version == 7
    assert settings is not None
    assert settings["theme"] == "system"


def test_schema_five_adds_source_origin_without_changing_existing_rows(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE libraries (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE sources (
            id TEXT PRIMARY KEY,
            library_id TEXT NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
            name TEXT NOT NULL, media_type TEXT NOT NULL, suffix TEXT NOT NULL,
            status TEXT NOT NULL, content_hash TEXT NOT NULL, size_bytes INTEGER NOT NULL,
            error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(library_id, content_hash)
        );
        INSERT INTO libraries VALUES ('lib', 'Keep', 'date', 'date');
        INSERT INTO sources VALUES (
            'source', 'lib', 'guide.md', 'text/markdown', '.md', 'ready',
            'hash', 12, NULL, 'date', 'date'
        );
        PRAGMA user_version=5;
        """
    )
    connection.close()

    database = AppDatabase(path)
    row = database.connection.execute(
        "SELECT source_kind, origin_url, name FROM sources WHERE id='source'"
    ).fetchone()

    assert database.connection.execute("PRAGMA user_version").fetchone()[0] == 7
    assert row is not None
    assert tuple(row) == ("file", None, "guide.md")
    database.close()


def test_running_model_job_is_recovered_as_pending(tmp_path: Path) -> None:
    database = AppDatabase(tmp_path / "app.sqlite")
    now = utc_timestamp()
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO model_jobs(
                id, model_id, status, bytes_total, created_at, updated_at
            ) VALUES ('model-job', 'model', 'running', 100, ?, ?)
            """,
            (now, now),
        )

    assert database.recover_model_jobs() == 1
    status = database.connection.execute(
        "SELECT status FROM model_jobs WHERE id='model-job'"
    ).fetchone()[0]
    database.close()

    assert status == "pending"


def test_running_jobs_are_recovered_as_pending(tmp_path: Path) -> None:
    database = AppDatabase(tmp_path / "app.sqlite")
    now = utc_timestamp()
    with database.transaction() as connection:
        connection.execute("INSERT INTO libraries VALUES ('lib', 'Library', ?, ?)", (now, now))
        connection.execute(
            """
            INSERT INTO jobs(
                id, library_id, kind, status, attempts, progress, created_at, updated_at
            ) VALUES ('job', 'lib', 'index', 'running', 1, 0.5, ?, ?)
            """,
            (now, now),
        )

    assert database.recover_interrupted_jobs() == 1
    status = database.connection.execute("SELECT status FROM jobs WHERE id='job'").fetchone()[0]
    database.close()

    assert status == "pending"


def test_interrupted_source_job_at_retry_limit_is_failed(tmp_path: Path) -> None:
    database = AppDatabase(tmp_path / "app.sqlite")
    now = utc_timestamp()
    with database.transaction() as connection:
        connection.execute("INSERT INTO libraries VALUES ('lib', 'Library', ?, ?)", (now, now))
        connection.execute(
            """
            INSERT INTO sources(
                id, library_id, name, media_type, suffix, status, content_hash,
                size_bytes, source_kind, origin_url, created_at, updated_at
            ) VALUES ('source', 'lib', 'a.txt', 'text/plain', '.txt', 'parsing',
                'hash', 1, 'file', NULL, ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO jobs(
                id, library_id, source_id, kind, status, attempts, progress, created_at, updated_at
            ) VALUES ('job', 'lib', 'source', 'index_source', 'running', 3, 0.5, ?, ?)
            """,
            (now, now),
        )

    assert database.recover_interrupted_jobs() == 1
    job = database.connection.execute("SELECT status, error FROM jobs WHERE id='job'").fetchone()
    source = database.connection.execute(
        "SELECT status, error FROM sources WHERE id='source'"
    ).fetchone()
    database.close()

    assert job is not None and job["status"] == "failed" and "retry limit" in job["error"]
    assert source is not None and source["status"] == "failed" and source["error"]


def test_layout_rejects_invalid_identifiers(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    layout.initialize()

    try:
        layout.library("../outside")
    except ValueError as error:
        assert "identifier" in str(error)
    else:
        raise AssertionError("Expected traversal identifier to be rejected")


def test_job_lease_heartbeat_and_backup(tmp_path: Path) -> None:
    database = AppDatabase(tmp_path / "app.sqlite")
    now = utc_timestamp()
    with database.transaction() as connection:
        connection.execute("INSERT INTO libraries VALUES ('lib', 'Library', ?, ?)", (now, now))
        connection.execute(
            """
            INSERT INTO jobs(
                id, library_id, kind, status, attempts, progress, created_at, updated_at
            ) VALUES ('job', 'lib', 'index', 'pending', 0, 0, ?, ?)
            """,
            (now, now),
        )

    leased = database.lease_next_job("worker")
    assert leased is not None
    assert leased["status"] == "running"
    assert leased["attempts"] == 1
    assert database.heartbeat("job", "worker") is True

    backup_path = tmp_path / "backup.sqlite"
    database.backup(backup_path)
    backup = AppDatabase(backup_path)
    assert backup.connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
    backup.close()
    database.close()
