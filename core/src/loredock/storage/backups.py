"""Consistent managed backups and restart-boundary restoration."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal, Protocol, TypedDict, cast
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

BACKUP_FORMAT_VERSION = 1
MAX_BACKUP_ENTRIES = 20_000
MAX_BACKUP_BYTES = 20 * 1024 * 1024 * 1024
MANIFEST_NAME = "backup-manifest.json"
PENDING_RESTORE_NAME = "pending-restore.json"


class BackupError(ValueError):
    """A managed backup is invalid or cannot be restored safely."""


@dataclass(frozen=True, slots=True)
class BackupInfo:
    id: str
    created_at: str
    size_bytes: int
    file_count: int
    status: Literal["valid", "invalid"]


class BackupDatabase(Protocol):
    def backup(self, destination: Path) -> None: ...


class BackupFile(TypedDict):
    path: str
    size_bytes: int
    sha256: str


class BackupManifest(TypedDict):
    format_version: int
    id: str
    created_at: str
    files: list[BackupFile]


def _parse_manifest(payload: bytes | str) -> BackupManifest:
    try:
        value: object = json.loads(payload)
        if not isinstance(value, dict):
            raise BackupError("Backup manifest is invalid.")
        manifest_object = cast(dict[str, object], value)
        if manifest_object.get("format_version") != BACKUP_FORMAT_VERSION:
            raise BackupError("Backup format is not supported.")
        raw_id = manifest_object.get("id")
        created_at = manifest_object.get("created_at")
        raw_files = manifest_object.get("files")
        if not isinstance(raw_id, str):
            raise BackupError("Backup manifest is invalid.")
        backup_id = _validate_id(raw_id)
        if not isinstance(created_at, str) or not isinstance(raw_files, list):
            raise BackupError("Backup manifest is invalid.")
        files: list[BackupFile] = []
        seen: set[str] = set()
        for raw_value in cast(list[object], raw_files):
            raw = cast(dict[str, object], raw_value) if isinstance(raw_value, dict) else None
            if not isinstance(raw, dict):
                raise BackupError("Backup manifest is invalid.")
            path = raw.get("path")
            size = raw.get("size_bytes")
            checksum = raw.get("sha256")
            if (
                not isinstance(path, str)
                or path in seen
                or not isinstance(size, int)
                or size < 0
                or not isinstance(checksum, str)
                or len(checksum) != 64
                or any(character not in "0123456789abcdef" for character in checksum)
            ):
                raise BackupError("Backup manifest is invalid.")
            seen.add(path)
            files.append({"path": path, "size_bytes": size, "sha256": checksum})
        return {
            "format_version": BACKUP_FORMAT_VERSION,
            "id": backup_id,
            "created_at": created_at,
            "files": files,
        }
    except (TypeError, json.JSONDecodeError) as error:
        raise BackupError("Backup manifest is invalid.") from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_id(backup_id: str) -> str:
    try:
        return str(UUID(backup_id))
    except ValueError as error:
        raise BackupError("Invalid backup identifier.") from error


def _check_sqlite(path: Path) -> None:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if result is None or result[0] != "ok":
            raise BackupError(f"SQLite integrity check failed for {path.name}.")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise BackupError(f"SQLite foreign-key check failed for {path.name}.")
    finally:
        connection.close()


def _backup_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


class BackupManager:
    def __init__(self, data_root: Path) -> None:
        self.root = data_root.resolve()
        self.backups = self.root / "backups"
        self.backups.mkdir(parents=True, exist_ok=True)

    def archive_path(self, backup_id: str) -> Path:
        return self.backups / f"{_validate_id(backup_id)}.loredock-backup"

    def create(self, app_database: BackupDatabase, libraries_root: Path) -> BackupInfo:
        backup_id = str(uuid4())
        created_at = datetime.now(UTC).isoformat()
        destination = self.archive_path(backup_id)
        temporary_archive = destination.with_suffix(".tmp")
        with TemporaryDirectory(prefix="loredock-backup-") as temporary:
            stage = Path(temporary)
            database_path = stage / "app.sqlite"
            app_database.backup(database_path)
            if libraries_root.exists():
                shutil.copytree(
                    libraries_root,
                    stage / "libraries",
                    ignore=shutil.ignore_patterns(
                        "index.sqlite", "index.sqlite-wal", "index.sqlite-shm"
                    ),
                )
                for index in libraries_root.rglob("index.sqlite"):
                    _backup_sqlite(index, stage / "libraries" / index.relative_to(libraries_root))
            else:
                (stage / "libraries").mkdir()
            sqlite_files = [database_path, *(stage / "libraries").rglob("index.sqlite")]
            for sqlite_file in sqlite_files:
                _check_sqlite(sqlite_file)
            files: list[BackupFile] = []
            for path in sorted(stage.rglob("*")):
                if path.is_symlink():
                    raise BackupError("Backup data cannot contain symbolic links.")
                if path.is_file():
                    relative = path.relative_to(stage).as_posix()
                    files.append(
                        {
                            "path": relative,
                            "size_bytes": path.stat().st_size,
                            "sha256": _sha256(path),
                        }
                    )
            manifest: BackupManifest = {
                "format_version": BACKUP_FORMAT_VERSION,
                "id": backup_id,
                "created_at": created_at,
                "files": files,
            }
            try:
                with ZipFile(temporary_archive, "w", compression=ZIP_DEFLATED) as archive:
                    archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False))
                    for item in files:
                        archive.write(stage / item["path"], item["path"])
                os.replace(temporary_archive, destination)
            finally:
                temporary_archive.unlink(missing_ok=True)
        return self.verify(backup_id)

    def verify(self, backup_id: str) -> BackupInfo:
        archive_path = self.archive_path(backup_id)
        if not archive_path.is_file():
            raise BackupError("Backup does not exist.")
        with TemporaryDirectory(prefix="loredock-verify-") as temporary:
            stage = Path(temporary)
            self._extract_verified(archive_path, stage)
            _check_sqlite(stage / "app.sqlite")
            for index in (stage / "libraries").rglob("index.sqlite"):
                _check_sqlite(index)
            manifest = _parse_manifest((stage / MANIFEST_NAME).read_bytes())
        return BackupInfo(
            id=backup_id,
            created_at=str(manifest["created_at"]),
            size_bytes=archive_path.stat().st_size,
            file_count=len(manifest["files"]),
            status="valid",
        )

    def list(self) -> list[BackupInfo]:
        records: list[BackupInfo] = []
        for archive in self.backups.glob("*.loredock-backup"):
            try:
                records.append(self.verify(archive.stem))
            except BackupError:
                records.append(BackupInfo(archive.stem, "", archive.stat().st_size, 0, "invalid"))
        return sorted(records, key=lambda item: (item.created_at, item.id), reverse=True)

    def schedule_restore(self, backup_id: str) -> BackupInfo:
        info = self.verify(backup_id)
        marker = self.root / PENDING_RESTORE_NAME
        temporary = marker.with_suffix(".tmp")
        temporary.write_text(json.dumps({"backup_id": backup_id}), encoding="utf-8")
        os.replace(temporary, marker)
        return info

    def _extract_verified(self, archive_path: Path, destination: Path) -> None:
        try:
            with ZipFile(archive_path) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_BACKUP_ENTRIES:
                    raise BackupError("Backup contains too many files.")
                if sum(item.file_size for item in entries) > MAX_BACKUP_BYTES:
                    raise BackupError("Backup expands beyond the safety limit.")
                names = {item.filename for item in entries}
                if MANIFEST_NAME not in names:
                    raise BackupError("Backup manifest is missing.")
                for item in entries:
                    path = PurePosixPath(item.filename)
                    if path.is_absolute() or ".." in path.parts or "\\" in item.filename:
                        raise BackupError("Backup contains an unsafe path.")
                manifest = _parse_manifest(archive.read(MANIFEST_NAME))
                if manifest["id"] != archive_path.name.removesuffix(".loredock-backup"):
                    raise BackupError("Backup identifier does not match its archive.")
                declared = {item["path"]: item for item in manifest["files"]}
                if set(declared) != names - {MANIFEST_NAME}:
                    raise BackupError("Backup manifest does not match archive contents.")
                archive.extractall(destination)
        except (BadZipFile, KeyError, TypeError, json.JSONDecodeError) as error:
            raise BackupError("Backup archive is invalid.") from error
        for relative, item in declared.items():
            path = destination / relative
            if path.stat().st_size != item["size_bytes"] or _sha256(path) != item["sha256"]:
                raise BackupError("Backup file checksum verification failed.")
        libraries = destination / "libraries"
        libraries.mkdir(exist_ok=True)
        if not (destination / "app.sqlite").is_file():
            raise BackupError("Backup is missing required data.")
        (destination / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    def apply_pending_restore(self) -> bool:
        marker = self.root / PENDING_RESTORE_NAME
        if not marker.is_file():
            return False
        try:
            backup_id = json.loads(marker.read_text(encoding="utf-8"))["backup_id"]
            archive = self.archive_path(backup_id)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise BackupError("Pending restore marker is invalid.") from error
        with TemporaryDirectory(dir=self.root, prefix="restore-stage-") as temporary:
            stage = Path(temporary)
            self._extract_verified(archive, stage)
            _check_sqlite(stage / "app.sqlite")
            rollback = self.root / f"restore-rollback-{uuid4()}"
            rollback.mkdir()
            current_database = self.root / "app.sqlite"
            current_libraries = self.root / "libraries"
            try:
                if current_database.exists():
                    os.replace(current_database, rollback / "app.sqlite")
                for suffix in ("-wal", "-shm"):
                    sidecar = self.root / f"app.sqlite{suffix}"
                    if sidecar.exists():
                        os.replace(sidecar, rollback / sidecar.name)
                if current_libraries.exists():
                    os.replace(current_libraries, rollback / "libraries")
                os.replace(stage / "app.sqlite", current_database)
                os.replace(stage / "libraries", current_libraries)
                _check_sqlite(current_database)
                marker.unlink()
            except Exception:
                current_database.unlink(missing_ok=True)
                if current_libraries.exists():
                    shutil.rmtree(current_libraries)
                if (rollback / "app.sqlite").exists():
                    os.replace(rollback / "app.sqlite", current_database)
                if (rollback / "libraries").exists():
                    os.replace(rollback / "libraries", current_libraries)
                for suffix in ("-wal", "-shm"):
                    sidecar = rollback / f"app.sqlite{suffix}"
                    if sidecar.exists():
                        os.replace(sidecar, self.root / sidecar.name)
                raise
            finally:
                if rollback.exists():
                    shutil.rmtree(rollback)
        return True
