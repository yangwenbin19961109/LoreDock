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

    assert version == 2


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
