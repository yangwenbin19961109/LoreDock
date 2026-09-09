"""Rebuildable per-library SQLite FTS5 + sqlite-vec index."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Literal, Protocol, cast

from loredock.retrieval.analyzer import fts_query, lexical_text
from loredock.retrieval.chunking import ParentSection, TextChunk
from loredock.retrieval.embeddings import EmbeddingProvider, Vector
from loredock.retrieval.fusion import reciprocal_rank_fusion
from loredock.version import INDEX_SCHEMA_VERSION


class SqliteVecModule(Protocol):
    def load(self, connection: sqlite3.Connection) -> None: ...

    def serialize_float32(self, vector: list[float]) -> bytes: ...


sqlite_vec = cast(SqliteVecModule, import_module("sqlite_vec"))
ContextStrategy = Literal["child", "adjacent", "parent"]


@dataclass(frozen=True, slots=True)
class CitationRange:
    char_start: int
    char_end: int
    page_start: int | None
    page_end: int | None


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunk_id: str
    source_id: str
    text: str
    score: float
    char_start: int
    char_end: int
    page: int | None
    title_path: tuple[str, ...]
    matched_chunk_id: str
    parent_id: str | None
    context_id: str
    context_text: str
    matched_range: CitationRange
    context_range: CitationRange


class HybridSearchIndex:
    """Derived index with no ownership of original source documents."""

    def __init__(self, path: Path, provider: EmbeddingProvider) -> None:
        self.path = path
        self.provider = provider
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.enable_load_extension(True)
        sqlite_vec.load(self.connection)
        self.connection.enable_load_extension(False)
        try:
            self._create_schema()
        except Exception:
            self.connection.close()
            raise

    def __enter__(self) -> HybridSearchIndex:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _create_schema(self) -> None:
        dimensions = self.provider.dimensions
        self.connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS index_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chunks (
                rowid INTEGER PRIMARY KEY,
                chunk_id TEXT NOT NULL UNIQUE,
                source_id TEXT NOT NULL,
                text TEXT NOT NULL,
                char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL,
                page INTEGER,
                title_path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                parent_id TEXT,
                ordinal INTEGER NOT NULL,
                previous_id TEXT,
                next_id TEXT
            );
            CREATE TABLE IF NOT EXISTS parents (
                parent_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL,
                page_start INTEGER,
                page_end INTEGER,
                title_path TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(lexical);
            """
        )
        expected = {
            "schema_version": str(INDEX_SCHEMA_VERSION),
            "embedding_provider": self.provider.identifier,
            "embedding_dimensions": str(dimensions),
            "embedding_normalized": "true",
        }
        existing = {
            str(row["key"]): str(row["value"])
            for row in self.connection.execute("SELECT key, value FROM index_metadata")
        }
        if existing and existing != expected:
            raise ValueError(
                "Index build contract does not match the configured embedding provider"
            )
        with self.connection:
            self.connection.executemany(
                "INSERT OR IGNORE INTO index_metadata(key, value) VALUES (?, ?)", expected.items()
            )
        self.connection.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
                rowid INTEGER PRIMARY KEY,
                embedding float[{dimensions}]
            );
            """
        )

    def add(self, chunks: Sequence[TextChunk], parents: Sequence[ParentSection] = ()) -> None:
        with self.connection:
            self._insert_parents(parents)
            self._insert_chunks(chunks)

    def _insert_parents(self, parents: Sequence[ParentSection]) -> None:
        self.connection.executemany(
            """
            INSERT INTO parents(
                parent_id, source_id, kind, text, char_start, char_end,
                page_start, page_end, title_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    parent.id,
                    parent.source_id,
                    parent.kind,
                    parent.text,
                    parent.char_start,
                    parent.char_end,
                    parent.page_start,
                    parent.page_end,
                    json.dumps(parent.title_path, ensure_ascii=False),
                )
                for parent in parents
            ],
        )

    def _insert_chunks(self, chunks: Sequence[TextChunk]) -> None:
        vectors = self.provider.embed_documents([chunk.text for chunk in chunks])
        for chunk, vector in zip(chunks, vectors, strict=True):
            cursor = self.connection.execute(
                """
                    INSERT INTO chunks (
                        chunk_id, source_id, text, char_start, char_end, page,
                        title_path, content_hash, parent_id, ordinal, previous_id, next_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                (
                    chunk.id,
                    chunk.source_id,
                    chunk.text,
                    chunk.char_start,
                    chunk.char_end,
                    chunk.page,
                    json.dumps(chunk.title_path, ensure_ascii=False),
                    chunk.content_hash,
                    chunk.parent_id,
                    chunk.ordinal,
                    chunk.previous_id,
                    chunk.next_id,
                ),
            )
            rowid = cursor.lastrowid
            if rowid is None:
                raise RuntimeError("SQLite did not return a chunk rowid")
            self.connection.execute(
                "INSERT INTO chunks_fts(rowid, lexical) VALUES (?, ?)",
                (rowid, lexical_text(chunk.text)),
            )
            self.connection.execute(
                "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)",
                (rowid, sqlite_vec.serialize_float32(list(vector))),
            )

    def _delete_source(self, source_id: str) -> None:
        rowids = [
            int(row["rowid"])
            for row in self.connection.execute(
                "SELECT rowid FROM chunks WHERE source_id = ?", (source_id,)
            )
        ]
        for rowid in rowids:
            self.connection.execute("DELETE FROM chunks_fts WHERE rowid = ?", (rowid,))
            self.connection.execute("DELETE FROM chunks_vec WHERE rowid = ?", (rowid,))
        self.connection.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
        self.connection.execute("DELETE FROM parents WHERE source_id = ?", (source_id,))

    def replace_source(
        self,
        source_id: str,
        chunks: Sequence[TextChunk],
        parents: Sequence[ParentSection] = (),
    ) -> None:
        if any(chunk.source_id != source_id for chunk in chunks):
            raise ValueError("All replacement chunks must belong to the same source")
        if any(parent.source_id != source_id for parent in parents):
            raise ValueError("All replacement parents must belong to the same source")
        vectors = self.provider.embed_documents([chunk.text for chunk in chunks])
        with self.connection:
            self._delete_source(source_id)
            self._insert_parents(parents)
            for chunk, vector in zip(chunks, vectors, strict=True):
                cursor = self.connection.execute(
                    """
                    INSERT INTO chunks (
                        chunk_id, source_id, text, char_start, char_end, page,
                        title_path, content_hash, parent_id, ordinal, previous_id, next_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.id,
                        chunk.source_id,
                        chunk.text,
                        chunk.char_start,
                        chunk.char_end,
                        chunk.page,
                        json.dumps(chunk.title_path, ensure_ascii=False),
                        chunk.content_hash,
                        chunk.parent_id,
                        chunk.ordinal,
                        chunk.previous_id,
                        chunk.next_id,
                    ),
                )
                rowid = cursor.lastrowid
                if rowid is None:
                    raise RuntimeError("SQLite did not return a chunk rowid")
                self.connection.execute(
                    "INSERT INTO chunks_fts(rowid, lexical) VALUES (?, ?)",
                    (rowid, lexical_text(chunk.text)),
                )
                self.connection.execute(
                    "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)",
                    (rowid, sqlite_vec.serialize_float32(list(vector))),
                )

    def delete_source(self, source_id: str) -> None:
        with self.connection:
            self._delete_source(source_id)

    def _lexical_ids(self, query: str, limit: int) -> list[str]:
        expression = fts_query(query)
        if not expression:
            return []
        rows = self.connection.execute(
            """
            SELECT chunks.chunk_id
            FROM chunks_fts
            JOIN chunks ON chunks.rowid = chunks_fts.rowid
            WHERE chunks_fts MATCH ?
            ORDER BY bm25(chunks_fts), chunks.chunk_id
            LIMIT ?
            """,
            (expression, limit),
        )
        return [str(row["chunk_id"]) for row in rows]

    def _vector_ids(self, vector: Vector, limit: int) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT chunks.chunk_id
            FROM chunks_vec
            JOIN chunks ON chunks.rowid = chunks_vec.rowid
            WHERE chunks_vec.embedding MATCH ? AND k = ?
            ORDER BY chunks_vec.distance, chunks.chunk_id
            """,
            (sqlite_vec.serialize_float32(list(vector)), limit),
        )
        return [str(row["chunk_id"]) for row in rows]

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        candidate_limit: int = 50,
        rrf_k: int = 60,
        lexical_only: bool = False,
        vector_only: bool = False,
        max_context_chars: int = 4000,
        context_strategy: ContextStrategy = "parent",
    ) -> list[SearchResult]:
        if lexical_only and vector_only:
            raise ValueError("lexical_only and vector_only cannot both be enabled")
        rankings: list[list[str]] = []
        if not vector_only:
            rankings.append(self._lexical_ids(query, candidate_limit))
        if not lexical_only:
            rankings.append(self._vector_ids(self.provider.embed_query(query), candidate_limit))
        fused = reciprocal_rank_fusion(rankings, k=rrf_k)
        results: list[SearchResult] = []
        seen_contexts: set[str] = set()
        for chunk_id, score in fused:
            row = self.connection.execute(
                "SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)
            ).fetchone()
            if row is None:
                continue
            parent = None
            if row["parent_id"] is not None:
                parent = self.connection.execute(
                    "SELECT * FROM parents WHERE parent_id = ?", (row["parent_id"],)
                ).fetchone()
            context = self._context_for(
                row,
                parent,
                max_context_chars=max_context_chars,
                context_strategy=context_strategy,
            )
            if context[0] in seen_contexts:
                continue
            seen_contexts.add(context[0])
            results.append(
                SearchResult(
                    chunk_id=str(row["chunk_id"]),
                    source_id=str(row["source_id"]),
                    text=str(row["text"]),
                    score=score,
                    char_start=int(row["char_start"]),
                    char_end=int(row["char_end"]),
                    page=int(row["page"]) if row["page"] is not None else None,
                    title_path=tuple(json.loads(str(row["title_path"]))),
                    matched_chunk_id=str(row["chunk_id"]),
                    parent_id=str(row["parent_id"]) if row["parent_id"] is not None else None,
                    context_id=context[0],
                    context_text=context[1],
                    matched_range=CitationRange(
                        int(row["char_start"]),
                        int(row["char_end"]),
                        int(row["page"]) if row["page"] is not None else None,
                        int(row["page"]) if row["page"] is not None else None,
                    ),
                    context_range=CitationRange(*context[2:]),
                )
            )
            if len(results) >= limit:
                break
        return results

    def _context_for(
        self,
        row: sqlite3.Row,
        parent: sqlite3.Row | None,
        *,
        max_context_chars: int,
        context_strategy: ContextStrategy,
    ) -> tuple[str, str, int, int, int | None, int | None]:
        """Return a bounded Parent or adjacent-Child range without changing ranking."""

        if max_context_chars < 1:
            raise ValueError("max_context_chars must be positive")
        if context_strategy == "child" or parent is None:
            start = int(row["char_start"])
            end = int(row["char_end"])
            return (
                str(row["chunk_id"]),
                str(row["text"]),
                start,
                end,
                int(row["page"]) if row["page"] is not None else None,
                int(row["page"]) if row["page"] is not None else None,
            )

        if context_strategy == "adjacent":
            neighbors = self.connection.execute(
                """
                SELECT * FROM chunks
                WHERE source_id=? AND ordinal BETWEEN ? AND ?
                ORDER BY ordinal
                """,
                (str(row["source_id"]), int(row["ordinal"]) - 1, int(row["ordinal"]) + 1),
            ).fetchall()
            selected = [item for item in neighbors if item["parent_id"] == row["parent_id"]]
            start = int(selected[0]["char_start"])
            end = int(selected[-1]["char_end"])
            if end - start > max_context_chars:
                selected = [row]
                start = int(row["char_start"])
                end = int(row["char_end"])
            relative_start = start - int(parent["char_start"])
            relative_end = end - int(parent["char_start"])
            text = str(parent["text"])[relative_start:relative_end]
            return (
                f"range:{row['source_id']}:{start}:{end}",
                text,
                start,
                end,
                int(selected[0]["page"]) if selected[0]["page"] is not None else None,
                int(selected[-1]["page"]) if selected[-1]["page"] is not None else None,
            )

        if int(parent["char_end"]) - int(parent["char_start"]) <= max_context_chars:
            return (
                str(parent["parent_id"]),
                str(parent["text"]),
                int(parent["char_start"]),
                int(parent["char_end"]),
                int(parent["page_start"]) if parent["page_start"] is not None else None,
                int(parent["page_end"]) if parent["page_end"] is not None else None,
            )

        parent_start = int(parent["char_start"])
        parent_end = int(parent["char_end"])
        matched_start = int(row["char_start"])
        matched_end = int(row["char_end"])
        matched_length = matched_end - matched_start
        remaining = max(0, max_context_chars - matched_length)
        start = max(parent_start, matched_start - remaining // 2)
        end = min(parent_end, start + max_context_chars)
        start = max(parent_start, end - max_context_chars)
        relative_start = start - parent_start
        relative_end = end - parent_start
        text = str(parent["text"])[relative_start:relative_end]
        context_id = f"range:{row['source_id']}:{start}:{end}"
        return (
            context_id,
            text,
            start,
            end,
            int(parent["page_start"]) if parent["page_start"] is not None else None,
            int(parent["page_end"]) if parent["page_end"] is not None else None,
        )
