"""Bounded, read-only access to untrusted Office Open XML packages."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Protocol, cast
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, ZipInfo


class XmlElement(Protocol):
    tag: str
    text: str | None
    attrib: Mapping[str, str]

    def __iter__(self) -> Iterator[XmlElement]: ...

    def findall(self, path: str) -> list[XmlElement]: ...

    def get(self, key: str, default: str | None = None) -> str | None: ...


class LxmlEtreeModule(Protocol):
    XMLSyntaxError: type[Exception]

    def XMLParser(
        self,
        *,
        resolve_entities: bool,
        no_network: bool,
        load_dtd: bool,
        huge_tree: bool,
        recover: bool,
    ) -> object: ...

    def fromstring(self, text: bytes, *, parser: object) -> XmlElement: ...


etree = cast(LxmlEtreeModule, import_module("lxml.etree"))

RELATIONSHIPS_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"
_UNSAFE_XML_DECLARATION = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


class OoxmlPackageError(ValueError):
    """Raised when an OOXML container is malformed, unsafe, or outside its bounds."""


@dataclass(frozen=True, slots=True)
class OoxmlLimits:
    max_members: int = 4096
    max_part_bytes: int = 32 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024
    max_compression_ratio: int = 250
    compression_ratio_floor_bytes: int = 1024 * 1024


@dataclass(frozen=True, slots=True)
class OoxmlRelationship:
    id: str
    type: str
    target: str
    external: bool


def _normalized_part_name(name: str) -> str:
    if not name or "\\" in name or name.startswith("/"):
        raise OoxmlPackageError("OOXML package contains an unsafe part name.")
    path = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise OoxmlPackageError("OOXML package contains an unsafe part name.")
    normalized = path.as_posix()
    if normalized != name.rstrip("/"):
        raise OoxmlPackageError("OOXML package contains a non-canonical part name.")
    return normalized


def _relationship_part_name(source_part: str) -> str:
    normalized = _normalized_part_name(source_part)
    directory, filename = posixpath.split(normalized)
    return posixpath.join(directory, "_rels", f"{filename}.rels")


def _resolved_relationship_target(source_part: str, target: str) -> str:
    if not target or "\\" in target:
        raise OoxmlPackageError("OOXML relationship contains an unsafe target.")
    if target.startswith("/"):
        candidate = target.lstrip("/")
    else:
        candidate = posixpath.join(posixpath.dirname(source_part), target)
    normalized = posixpath.normpath(candidate)
    if normalized == ".." or normalized.startswith("../"):
        raise OoxmlPackageError("OOXML relationship escapes the package root.")
    return _normalized_part_name(normalized)


class OoxmlPackage:
    """Validate an OOXML ZIP once and expose only bounded in-memory reads."""

    def __init__(self, path: Path, *, limits: OoxmlLimits | None = None) -> None:
        self.path = path
        self.limits = limits or OoxmlLimits()
        try:
            self._archive = ZipFile(path, "r")
            self._parts = self._validate_members(self._archive.infolist())
        except (BadZipFile, OSError) as error:
            if hasattr(self, "_archive"):
                self._archive.close()
            raise OoxmlPackageError("The file is not a readable OOXML package.") from error
        except Exception:
            if hasattr(self, "_archive"):
                self._archive.close()
            raise

    def __enter__(self) -> OoxmlPackage:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def close(self) -> None:
        self._archive.close()

    @property
    def part_names(self) -> tuple[str, ...]:
        return tuple(self._parts)

    def has_part(self, name: str) -> bool:
        return _normalized_part_name(name) in self._parts

    def read_part(self, name: str) -> bytes:
        normalized = _normalized_part_name(name)
        info = self._parts.get(normalized)
        if info is None:
            raise OoxmlPackageError(f"OOXML package is missing required part: {normalized}")
        with self._archive.open(info, "r") as stream:
            payload = stream.read(self.limits.max_part_bytes + 1)
        if len(payload) > self.limits.max_part_bytes:
            raise OoxmlPackageError("OOXML part exceeds the safe decompression limit.")
        return payload

    def read_xml(self, name: str) -> XmlElement:
        payload = self.read_part(name)
        if _UNSAFE_XML_DECLARATION.search(payload):
            raise OoxmlPackageError("OOXML XML declarations may not define DTDs or entities.")
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            huge_tree=False,
            recover=False,
        )
        try:
            return etree.fromstring(payload, parser=parser)
        except etree.XMLSyntaxError as error:
            raise OoxmlPackageError(f"OOXML part is not valid XML: {name}") from error

    def relationships(self, source_part: str) -> tuple[OoxmlRelationship, ...]:
        relationship_part = _relationship_part_name(source_part)
        if relationship_part not in self._parts:
            return ()
        root = self.read_xml(relationship_part)
        relationships: list[OoxmlRelationship] = []
        for element in root:
            if element.tag.rsplit("}", 1)[-1] != "Relationship":
                continue
            relationship_id = (element.get("Id") or "").strip()
            relationship_type = (element.get("Type") or "").strip()
            raw_target = (element.get("Target") or "").strip()
            if not relationship_id or not relationship_type or not raw_target:
                raise OoxmlPackageError("OOXML relationship is missing required attributes.")
            external = (element.get("TargetMode") or "").casefold() == "external"
            target = (
                raw_target if external else _resolved_relationship_target(source_part, raw_target)
            )
            relationships.append(
                OoxmlRelationship(relationship_id, relationship_type, target, external)
            )
        return tuple(relationships)

    def _validate_members(self, members: list[ZipInfo]) -> dict[str, ZipInfo]:
        if len(members) > self.limits.max_members:
            raise OoxmlPackageError("OOXML package contains too many parts.")
        parts: dict[str, ZipInfo] = {}
        total_size = 0
        for info in members:
            normalized = _normalized_part_name(info.filename)
            if info.is_dir():
                continue
            if normalized in parts:
                raise OoxmlPackageError("OOXML package contains duplicate part names.")
            if info.flag_bits & 0x1:
                raise OoxmlPackageError("Encrypted OOXML parts are not supported.")
            if info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
                raise OoxmlPackageError("OOXML package uses an unsupported compression method.")
            if info.file_size > self.limits.max_part_bytes:
                raise OoxmlPackageError("OOXML part exceeds the safe decompression limit.")
            total_size += info.file_size
            if total_size > self.limits.max_total_bytes:
                raise OoxmlPackageError("OOXML package exceeds the total decompression limit.")
            if info.file_size >= self.limits.compression_ratio_floor_bytes:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > self.limits.max_compression_ratio:
                    raise OoxmlPackageError("OOXML package has an unsafe compression ratio.")
            parts[normalized] = info
        return parts
