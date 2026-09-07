"""Replaceable document parsing primitives."""

from loredock.ingestion.ooxml import (
    OoxmlLimits,
    OoxmlPackage,
    OoxmlPackageError,
    OoxmlRelationship,
)
from loredock.ingestion.parsers import ParsedDocument, parse_path
from loredock.ingestion.web import UrlFetcher, WebFetchError, WebSnapshot

__all__ = [
    "OoxmlLimits",
    "OoxmlPackage",
    "OoxmlPackageError",
    "OoxmlRelationship",
    "ParsedDocument",
    "UrlFetcher",
    "WebFetchError",
    "WebSnapshot",
    "parse_path",
]
