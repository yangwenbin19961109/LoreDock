import sqlite3
from pathlib import Path

from loredock.storage import AppDatabase, DataLayout
from loredock.storage.database import utc_timestamp


def test_migration_is_retry_safe(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite"
    first = AppDatabase(path)
    first.close()
    second = AppDatabase(path)

    version = second.connection.execute("PRAGMA user_version").fetchone()[0]
    second.close()

    assert version == 5


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
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version=2")
    connection.close()

    database = AppDatabase(path)
    version = database.connection.execute("PRAGMA user_version").fetchone()[0]
    settings = database.connection.execute("SELECT theme FROM app_settings WHERE id=1").fetchone()
    database.close()

    assert version == 5
    assert settings is not None
    assert settings["theme"] == "system"


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


def test_running_jobs_are_recovered_as_failed(tmp_path: Path) -> None:
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

    assert status == "failed"


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
