"""Replaceable document parsing primitives."""

from loredock.ingestion.ooxml import (
    OoxmlLimits,
    OoxmlPackage,
    OoxmlPackageError,
    OoxmlRelationship,
)
from loredock.ingestion.parsers import ParsedDocument, parse_path

__all__ = [
    "OoxmlLimits",
    "OoxmlPackage",
    "OoxmlPackageError",
    "OoxmlRelationship",
    "ParsedDocument",
    "parse_path",
]
