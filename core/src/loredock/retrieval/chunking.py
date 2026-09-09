"""Structure-aware, citation-preserving text chunking."""

import hashlib
import re
from dataclasses import dataclass, replace
from itertools import pairwise
from typing import Literal

from loredock.ingestion.parsers import ParsedDocument

_HEADING = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
_FENCED_CODE = re.compile(r"(?ms)^```[^\n]*\n.*?^```[ \t]*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$")
_TOKEN = re.compile(r"[\u3400-\u9fff]|[\w]+|[^\w\s]", re.UNICODE)
ChunkingStrategy = Literal["generic", "semantic_markdown"]


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    target_tokens: int = 512
    max_tokens: int = 768
    overlap_tokens: int = 64
    # A strategy/version change changes deterministic IDs and requires a rebuild.
    version: int = 1
    strategy: ChunkingStrategy = "generic"

    def __post_init__(self) -> None:
        if not 0 <= self.overlap_tokens < self.target_tokens <= self.max_tokens:
            raise ValueError("Expected 0 <= overlap < target <= max")
        if self.strategy not in {"generic", "semantic_markdown"}:
            raise ValueError("Unsupported chunking strategy")


@dataclass(frozen=True, slots=True)
class TextChunk:
    id: str
    source_id: str
    text: str
    char_start: int
    char_end: int
    page: int | None
    title_path: tuple[str, ...]
    content_hash: str
    parent_id: str | None = None
    ordinal: int = 0
    previous_id: str | None = None
    next_id: str | None = None


@dataclass(frozen=True, slots=True)
class ParentSection:
    id: str
    source_id: str
    kind: str
    text: str
    char_start: int
    char_end: int
    page_start: int | None
    page_end: int | None
    title_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ChunkedDocument:
    parents: tuple[ParentSection, ...]
    chunks: tuple[TextChunk, ...]


@dataclass(frozen=True, slots=True)
class _ParentRange:
    start: int
    end: int
    kind: str


_DEFAULT_CONFIG = ChunkingConfig()


def _token_spans(text: str, start: int = 0, end: int | None = None) -> list[tuple[int, int]]:
    """Return token spans constrained to an exact source range."""

    limit = len(text) if end is None else end
    return [
        (match.start(), match.end())
        for match in _TOKEN.finditer(text, start, limit)
        if match.end() <= limit
    ]


def _title_path_at(headings: list[tuple[int, int, str]], offset: int) -> tuple[str, ...]:
    path: list[str] = []
    for position, level, title in headings:
        if position > offset:
            break
        path = path[: level - 1]
        path.append(title)
    return tuple(path)


def _heading_data(
    text: str, excluded: tuple[tuple[int, int], ...] = ()
) -> list[tuple[int, int, str]]:
    def is_excluded(position: int) -> bool:
        return any(start <= position < end for start, end in excluded)

    return [
        (match.start(), len(match.group(1)), match.group(2).strip())
        for match in _HEADING.finditer(text)
        if not is_excluded(match.start())
    ]


def _markdown_tables(text: str, excluded: tuple[tuple[int, int], ...]) -> list[tuple[int, int]]:
    """Find complete pipe-table regions without interpreting content inside code fences."""

    lines = list(re.finditer(r".*(?:\n|$)", text))

    def is_excluded(position: int) -> bool:
        return any(start <= position < end for start, end in excluded)

    ranges: list[tuple[int, int]] = []
    index = 0
    while index + 1 < len(lines):
        header = lines[index]
        separator = lines[index + 1]
        header_text = header.group().rstrip("\r\n")
        separator_text = separator.group().rstrip("\r\n")
        if (
            is_excluded(header.start())
            or "|" not in header_text
            or not _TABLE_SEPARATOR.fullmatch(separator_text)
        ):
            index += 1
            continue
        end_index = index + 2
        while end_index < len(lines):
            row = lines[end_index]
            row_text = row.group().rstrip("\r\n")
            if is_excluded(row.start()) or "|" not in row_text or not row_text.strip():
                break
            end_index += 1
        ranges.append((header.start(), lines[end_index - 1].end()))
        index = end_index
    return ranges


def _is_faq_path(title_path: tuple[str, ...]) -> bool:
    return any("faq" in title.casefold() or "常见问题" in title for title in title_path)


def _semantic_parent_ranges(
    document: ParsedDocument, headings: list[tuple[int, int, str]]
) -> list[_ParentRange]:
    """Keep heading sections intact while attaching a semantic Parent kind to each one.

    Splitting a short heading section immediately before and after a table or fenced code
    block increases retrieval candidates without adding useful context. A complete section
    instead remains one Parent; its type guides context handling while ranked Child text and
    offsets stay identical to the established generic baseline.
    """

    code_ranges = tuple(
        (match.start(), match.end()) for match in _FENCED_CODE.finditer(document.text)
    )
    table_ranges = _markdown_tables(document.text, code_ranges)
    boundaries = sorted({0, len(document.text), *(position for position, _, _ in headings)})
    ranges: list[_ParentRange] = []
    for start, end in pairwise(boundaries):
        if not _token_spans(document.text, start, end):
            continue
        title_path = _title_path_at(headings, start)
        if _is_faq_path(title_path):
            kind = "faq"
        elif any(
            start <= table_start and table_end <= end for table_start, table_end in table_ranges
        ):
            kind = "table"
        elif any(start <= code_start and code_end <= end for code_start, code_end in code_ranges):
            kind = "code_scope"
        else:
            kind = "section" if title_path else "document_range"
        ranges.append(_ParentRange(start, end, kind))
    return ranges


def _generic_parent_ranges(
    document: ParsedDocument, headings: list[tuple[int, int, str]]
) -> list[_ParentRange]:
    """Preserve title-path grouping for controlled evaluation comparisons."""

    if not _token_spans(document.text):
        return []
    boundaries = sorted({0, len(document.text), *(position for position, _, _ in headings)})
    return [
        _ParentRange(start, end, "section" if _title_path_at(headings, start) else "document_range")
        for start, end in pairwise(boundaries)
        if _token_spans(document.text, start, end)
    ]


def _chunks_for_range(
    document: ParsedDocument,
    parent_range: _ParentRange,
    headings: list[tuple[int, int, str]],
    config: ChunkingConfig,
) -> list[TextChunk]:
    spans = _token_spans(document.text, parent_range.start, parent_range.end)
    if not spans:
        return []
    chunks: list[TextChunk] = []
    start_token = 0
    while start_token < len(spans):
        end_token = min(start_token + config.target_tokens, len(spans))
        hard_end = min(start_token + config.max_tokens, len(spans))
        if end_token < len(spans):
            paragraph_break = document.text.rfind(
                "\n\n", spans[start_token][0], spans[hard_end - 1][1]
            )
            if paragraph_break > spans[start_token][0]:
                candidate = next(
                    (
                        index
                        for index in range(end_token, hard_end)
                        if spans[index][0] >= paragraph_break
                    ),
                    end_token,
                )
                end_token = max(end_token, candidate)
        char_start = spans[start_token][0]
        char_end = spans[end_token - 1][1]
        text = document.text[char_start:char_end]
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        stable_key = f"{document.source_id}:{char_start}:{char_end}:{config.version}:{digest}"
        chunks.append(
            TextChunk(
                id=hashlib.sha256(stable_key.encode()).hexdigest()[:32],
                source_id=document.source_id,
                text=text,
                char_start=char_start,
                char_end=char_end,
                page=document.page_at(char_start),
                title_path=_title_path_at(headings, char_start),
                content_hash=digest,
            )
        )
        if end_token == len(spans):
            break
        start_token = max(start_token + 1, end_token - config.overlap_tokens)
    return chunks


def chunk_document(
    document: ParsedDocument, config: ChunkingConfig = _DEFAULT_CONFIG
) -> list[TextChunk]:
    """Chunk text on token boundaries while retaining exact character offsets."""

    return list(chunk_document_hierarchy(document, config).chunks)


def chunk_document_hierarchy(
    document: ParsedDocument, config: ChunkingConfig = _DEFAULT_CONFIG
) -> ChunkedDocument:
    """Build ranked Child chunks and rebuildable, strategy-selected Parent sections."""

    code_ranges = tuple(
        (match.start(), match.end()) for match in _FENCED_CODE.finditer(document.text)
    )
    headings = _heading_data(document.text, code_ranges)
    ranges = (
        _semantic_parent_ranges(document, headings)
        if config.strategy == "semantic_markdown"
        else _generic_parent_ranges(document, headings)
    )
    parents: list[ParentSection] = []
    enriched: list[TextChunk] = []
    for parent_range in ranges:
        children = _chunks_for_range(document, parent_range, headings, config)
        if not children:
            continue
        char_start = children[0].char_start
        char_end = children[-1].char_end
        title_path = _title_path_at(headings, char_start)
        stable_key = (
            f"{document.source_id}:{char_start}:{char_end}:parent:{config.version}:"
            f"{parent_range.kind}:{'/'.join(title_path)}"
        )
        parent_id = hashlib.sha256(stable_key.encode()).hexdigest()[:32]
        parents.append(
            ParentSection(
                id=parent_id,
                source_id=document.source_id,
                kind=parent_range.kind,
                text=document.text[char_start:char_end],
                char_start=char_start,
                char_end=char_end,
                page_start=document.page_at(char_start),
                page_end=document.page_at(max(char_start, char_end - 1)),
                title_path=title_path,
            )
        )
        for chunk in children:
            enriched.append(replace(chunk, parent_id=parent_id, ordinal=len(enriched)))

    linked = [
        replace(
            chunk,
            previous_id=enriched[index - 1].id if index > 0 else None,
            next_id=enriched[index + 1].id if index + 1 < len(enriched) else None,
        )
        for index, chunk in enumerate(enriched)
    ]
    return ChunkedDocument(tuple(parents), tuple(linked))
