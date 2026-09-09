from io import BytesIO
from pathlib import Path

import pytest

from loredock.application.errors import AppError
from loredock.application.service import LoreDockService
from loredock.retrieval import HashingEmbeddingProvider


def test_backup_restore_round_trip_at_restart_boundary(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    library = service.create_library("Before backup")
    source = service.import_source(
        library.id, "notes.txt", "text/plain", BytesIO(b"restored searchable phrase")
    )[0]
    service.set_source_favorite(source.id, True)
    backup = service.create_backup()

    assert backup.status == "valid"
    assert backup.file_count >= 4
    assert service.verify_backup(backup.id) == backup
    assert service.list_backups() == [backup]

    service.rename_library(library.id, "After backup")
    service.delete_source(source.id)
    service.schedule_backup_restore(backup.id)
    service.close()

    restored = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    try:
        assert restored.get_library(library.id).name == "Before backup"
        assert restored.get_source(source.id).name == "notes.txt"
        assert restored.source_is_favorite(source.id)
        assert restored.search(library.id, "restored searchable phrase", lexical_only=True)
        assert not (tmp_path / "pending-restore.json").exists()
    finally:
        restored.close()


def test_corrupt_backup_is_rejected_without_scheduling_restore(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    try:
        service.create_library("Fixture")
        backup = service.create_backup()
        archive = tmp_path / "backups" / f"{backup.id}.loredock-backup"
        archive.write_bytes(archive.read_bytes()[:32])

        with pytest.raises(AppError) as error:
            service.schedule_backup_restore(backup.id)

        assert error.value.code == "backup_invalid"
        assert not (tmp_path / "pending-restore.json").exists()
        assert service.list_backups()[0].status == "invalid"
    finally:
        service.close()
