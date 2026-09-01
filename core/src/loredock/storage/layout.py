"""Validated LoreDock data-directory layout."""

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LibraryPaths:
    root: Path
    raw: Path
    artifacts: Path
    index: Path
    manifest: Path


class DataLayout:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.libraries = self.root / "libraries"

    def initialize(self) -> None:
        self.libraries.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_identifier(identifier: str) -> None:
        if not identifier or any(character not in "0123456789abcdef-" for character in identifier):
            raise ValueError("Invalid storage identifier")

    def library(self, library_id: str) -> LibraryPaths:
        self._validate_identifier(library_id)
        root = (self.libraries / library_id).resolve()
        if not root.is_relative_to(self.libraries):
            raise ValueError("Library path escapes the data directory")
        return LibraryPaths(
            root=root,
            raw=root / "raw",
            artifacts=root / "artifacts",
            index=root / "index.sqlite",
            manifest=root / "manifest.json",
        )

    def create_library(self, library_id: str) -> LibraryPaths:
        paths = self.library(library_id)
        paths.raw.mkdir(parents=True, exist_ok=False)
        paths.artifacts.mkdir(parents=True, exist_ok=False)
        return paths

    def delete_library(self, library_id: str) -> None:
        paths = self.library(library_id)
        if paths.root.exists():
            shutil.rmtree(paths.root)

    def source_raw_path(self, library_id: str, source_id: str, suffix: str) -> Path:
        self._validate_identifier(source_id)
        if suffix and (not suffix.startswith(".") or any(char in suffix for char in "/\\")):
            raise ValueError("Invalid source suffix")
        path = (self.library(library_id).raw / f"{source_id}{suffix.lower()}").resolve()
        if not path.is_relative_to(self.library(library_id).raw):
            raise ValueError("Source path escapes the library")
        return path
