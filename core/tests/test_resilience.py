import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import pytest

from loredock.application import LoreDockService
from loredock.application.errors import AppError
from loredock.retrieval import HashingEmbeddingProvider


def test_repeated_import_and_search_remains_consistent(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    library = service.create_library("Soak")
    try:
        for index in range(30):
            service.import_source(
                library.id,
                f"source-{index}.txt",
                "text/plain",
                BytesIO(f"stable repeated content {index}".encode()),
            )
        for index in range(100):
            results = service.search(library.id, f"content {index % 30}", lexical_only=True)
            assert results
        assert len(service.list_sources(library.id)) == 30
    finally:
        service.close()


def test_failed_source_write_leaves_no_partial_file(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    library = service.create_library("Full disk")

    class InterruptedStream(BytesIO):
        reads = 0

        def read(self, size: int | None = -1) -> bytes:
            self.reads += 1
            if self.reads > 1:
                raise OSError("No space left on device")
            return super().read(size)

    try:
        with pytest.raises(OSError, match="No space left"):
            service.import_source(
                library.id, "partial.txt", "text/plain", InterruptedStream(b"partial")
            )
        assert list(service.layout.library(library.id).raw.iterdir()) == []
    finally:
        service.close()


def test_metadata_disk_full_removes_completed_raw_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    library = service.create_library("Metadata full")

    @contextmanager
    def disk_full_transaction() -> Generator[sqlite3.Connection]:
        raise sqlite3.OperationalError("database or disk is full")
        yield service.database.connection

    monkeypatch.setattr(service.database, "transaction", disk_full_transaction)
    try:
        with pytest.raises(AppError) as caught:
            service.import_source(
                library.id, "complete.txt", "text/plain", BytesIO(b"complete copy")
            )
        assert caught.value.code == "source_store_failed"
        assert caught.value.status_code == 507
        assert list(service.layout.library(library.id).raw.iterdir()) == []
    finally:
        service.close()


def test_corrupt_index_and_stale_rebuild_are_recovered_from_source(tmp_path: Path) -> None:
    service = LoreDockService(tmp_path, HashingEmbeddingProvider(32))
    library = service.create_library("Recovery")
    source, _, _ = service.import_source(
        library.id, "source.txt", "text/plain", BytesIO(b"recoverable original source")
    )
    paths = service.layout.library(library.id)
    paths.index.write_bytes(b"not a sqlite database")
    stale = paths.index.with_name(f"{paths.index.name}.rebuild")
    stale.write_bytes(b"interrupted rebuild")

    try:
        results = service.search(library.id, "recoverable", lexical_only=True)
        assert results[0].source_id == source.id
        assert not stale.exists()
    finally:
        service.close()
