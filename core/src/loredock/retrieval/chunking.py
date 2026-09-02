"""Structure-aware, citation-preserving text chunking."""

import hashlib
import re
from dataclasses import dataclass, replace

from loredock.ingestion.parsers import ParsedDocument

_HEADING = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
_TOKEN = re.compile(r"[\u3400-\u9fff]|[\w]+|[^\w\s]", re.UNICODE)


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    target_tokens: int = 512
    max_tokens: int = 768
    overlap_tokens: int = 64
    version: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.overlap_tokens < self.target_tokens <= self.max_tokens:
            raise ValueError("Expected 0 <= overlap < target <= max")


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


_DEFAULT_CONFIG = ChunkingConfig()


def _token_spans(text: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in _TOKEN.finditer(text)]


def _title_path_at(headings: list[tuple[int, int, str]], offset: int) -> tuple[str, ...]:
    path: list[str] = []
    for position, level, title in headings:
        if position > offset:
            break
        path = path[: level - 1]
        path.append(title)
    return tuple(path)


def chunk_document(
    document: ParsedDocument, config: ChunkingConfig = _DEFAULT_CONFIG
) -> list[TextChunk]:
    """Chunk text on token boundaries while retaining exact character offsets."""

    return list(chunk_document_hierarchy(document, config).chunks)


def chunk_document_hierarchy(
    document: ParsedDocument, config: ChunkingConfig = _DEFAULT_CONFIG
) -> ChunkedDocument:
    """Build ranked Child chunks and rebuildable structural Parent sections."""

    spans = _token_spans(document.text)
    if not spans:
        return ChunkedDocument((), ())
    headings = [
        (match.start(), len(match.group(1)), match.group(2).strip())
        for match in _HEADING.finditer(document.text)
    ]
    chunks: list[TextChunk] = []
    start_token = 0
    while start_token < len(spans):
        char_start = spans[start_token][0]
        end_token = min(start_token + config.target_tokens, len(spans))
        hard_end = min(start_token + config.max_tokens, len(spans))
        ended_at_heading = False
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
        next_heading = next(
            (position for position, _, _ in headings if position > char_start), None
        )
        if next_heading is not None and next_heading < spans[end_token - 1][1]:
            heading_token = next(
                (
                    index
                    for index in range(start_token + 1, end_token)
                    if spans[index][0] >= next_heading
                ),
                None,
            )
            if heading_token is not None:
                end_token = heading_token
                ended_at_heading = True
        char_end = spans[end_token - 1][1]
        text = document.text[char_start:char_end]
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        stable_key = f"{document.source_id}:{char_start}:{char_end}:{config.version}:{digest}"
        chunk_id = hashlib.sha256(stable_key.encode()).hexdigest()[:32]
        chunks.append(
            TextChunk(
                id=chunk_id,
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
        start_token = (
            end_token
            if ended_at_heading
            else max(start_token + 1, end_token - config.overlap_tokens)
        )
    groups: list[list[TextChunk]] = []
    for chunk in chunks:
        if not groups or groups[-1][-1].title_path != chunk.title_path:
            groups.append([])
        groups[-1].append(chunk)

    parents: list[ParentSection] = []
    enriched: list[TextChunk] = []
    for group in groups:
        char_start = group[0].char_start
        char_end = group[-1].char_end
        stable_key = (
            f"{document.source_id}:{char_start}:{char_end}:parent:{config.version}:"
            f"{'/'.join(group[0].title_path)}"
        )
        parent_id = hashlib.sha256(stable_key.encode()).hexdigest()[:32]
        parents.append(
            ParentSection(
                id=parent_id,
                source_id=document.source_id,
                kind="section" if group[0].title_path else "document_range",
                text=document.text[char_start:char_end],
                char_start=char_start,
                char_end=char_end,
                page_start=document.page_at(char_start),
                page_end=document.page_at(max(char_start, char_end - 1)),
                title_path=group[0].title_path,
            )
        )
        for chunk in group:
            ordinal = len(enriched)
            enriched.append(replace(chunk, parent_id=parent_id, ordinal=ordinal))

    linked = [
        replace(
            chunk,
            previous_id=enriched[index - 1].id if index > 0 else None,
            next_id=enriched[index + 1].id if index + 1 < len(enriched) else None,
        )
        for index, chunk in enumerate(enriched)
    ]
    return ChunkedDocument(tuple(parents), tuple(linked))
