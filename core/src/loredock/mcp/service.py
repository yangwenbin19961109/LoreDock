"""Authorized projections of the same use cases used by HTTP adapters."""

from dataclasses import asdict

from loredock.api.pagination import SourceCursor, decode_source_cursor, encode_source_cursor
from loredock.application import LoreDockService
from loredock.application.errors import AppError
from loredock.application.records import SourceRecord
from loredock.mcp.contracts import (
    IndexStatus,
    KnowledgeHit,
    KnowledgeResults,
    LibraryList,
    LibraryRequest,
    LibrarySummary,
    ListLibrariesRequest,
    ListSourcesRequest,
    ReadSourceRequest,
    SearchKnowledgeRequest,
    SourceExcerpt,
    SourceInfoRequest,
    SourceList,
    SourceSummary,
)


class McpToolService:
    """Trusted caller supplies scope; tool arguments cannot enlarge it.

    Instances are request/session scoped. Transport authentication must resolve
    current grants before constructing this adapter; this is not authentication.
    """

    def __init__(
        self, core: LoreDockService, *, allowed_library_ids: frozenset[str] = frozenset()
    ) -> None:
        self._core = core
        self._allowed = allowed_library_ids

    def _authorize(self, library_id: str) -> None:
        if library_id not in self._allowed:
            raise AppError("access_denied", "Library access is not permitted.", status_code=403)

    @staticmethod
    def _source_summary(source: SourceRecord) -> SourceSummary:
        # Deliberately omit raw error text and internal paths from Agent metadata.
        return SourceSummary(
            id=source.id,
            library_id=source.library_id,
            name=source.name[:240],
            media_type=source.media_type[:120],
            status=source.status,
            size_bytes=source.size_bytes,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )

    def get_source_info(self, request: SourceInfoRequest) -> SourceSummary:
        self._authorize(request.library_id)
        source = self._core.get_source(request.source_id)
        if source.library_id != request.library_id:
            raise AppError("access_denied", "Source access is not permitted.", status_code=403)
        return self._source_summary(source)

    def list_sources(self, request: ListSourcesRequest) -> SourceList:
        self._authorize(request.library_id)
        # Bind the opaque cursor to its library, unlike the general HTTP cursor.
        cursor = (
            decode_source_cursor(
                request.cursor, sort="updated-desc", filter_text=request.library_id
            )
            if request.cursor is not None
            else None
        )
        records, has_more = self._core.list_sources_page(
            request.library_id,
            limit=request.limit,
            after_value=cursor.value if cursor else None,
            after_id=cursor.source_id if cursor else None,
        )
        next_cursor = None
        if records and has_more:
            last = records[-1]
            next_cursor = encode_source_cursor(
                SourceCursor("updated-desc", request.library_id, last.updated_at, last.id)
            )
        return SourceList(
            items=[self._source_summary(source) for source in records], next_cursor=next_cursor
        )

    def get_index_status(self, request: LibraryRequest) -> IndexStatus:
        self._authorize(request.library_id)
        return IndexStatus.model_validate(asdict(self._core.get_index_status(request.library_id)))

    def list_libraries(self, request: ListLibrariesRequest) -> LibraryList:
        records = sorted(
            (item for item in self._core.list_libraries() if item.id in self._allowed),
            key=lambda item: item.id,
        )
        if request.after_id is not None:
            records = [item for item in records if item.id > request.after_id]
        page = records[: request.limit]
        return LibraryList(
            items=[LibrarySummary(id=item.id, name=item.name) for item in page],
            next_after_id=page[-1].id if len(records) > request.limit else None,
        )

    def search_knowledge(self, request: SearchKnowledgeRequest) -> KnowledgeResults:
        self._authorize(request.library_id)
        results = self._core.search(
            request.library_id,
            request.query,
            limit=request.limit,
            lexical_only=request.lexical_only,
        )
        items: list[KnowledgeHit] = []
        for hit in results:
            source = self._core.get_source(hit.source_id)
            if source.library_id != request.library_id:
                raise AppError("access_denied", "Source access is not permitted.", status_code=403)
            # Clip text only, never reorder candidates or mislabel citation offsets.
            text = hit.text[:1600]
            items.append(
                KnowledgeHit(
                    library_id=request.library_id,
                    source_id=hit.source_id,
                    source_name=source.name[:240],
                    chunk_id=hit.chunk_id,
                    parent_id=hit.parent_id,
                    text=text,
                    score=hit.score,
                    char_start=hit.char_start,
                    char_end=hit.char_start + len(text),
                    matched_char_end=hit.char_end,
                    page=hit.page,
                    title_path=tuple(part[:200] for part in hit.title_path[:8]),
                    truncated=len(text) < len(hit.text),
                    read_reference=ReadSourceRequest(
                        library_id=request.library_id,
                        source_id=hit.source_id,
                        start=hit.char_start,
                    ),
                )
            )
        return KnowledgeResults(items=items)

    def read_source(self, request: ReadSourceRequest) -> SourceExcerpt:
        self._authorize(request.library_id)
        source = self._core.get_source(request.source_id)
        if source.library_id != request.library_id:
            raise AppError("access_denied", "Source access is not permitted.", status_code=403)
        # Probe one extra character to distinguish end-of-source from a full page.
        content = self._core.read_source(
            request.source_id, request.start, request.start + request.length + 1
        )
        text = content.text[: request.length]
        end = content.char_start + len(text)
        return SourceExcerpt(
            library_id=request.library_id,
            source_id=request.source_id,
            text=text,
            char_start=content.char_start,
            char_end=end,
            next_start=end if len(content.text) > request.length else None,
        )
