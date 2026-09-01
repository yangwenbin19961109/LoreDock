"""Disposable per-experiment SQLite FTS5 + sqlite-vec index."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

from loredock.retrieval.analyzer import fts_query, lexical_text
from loredock.retrieval.chunking import TextChunk
from loredock.retrieval.embeddings import EmbeddingProvider, Vector
from loredock.retrieval.fusion import reciprocal_rank_fusion


class SqliteVecModule(Protocol):
    def load(self, connection: sqlite3.Connection) -> None: ...

    def serialize_float32(self, vector: list[float]) -> bytes: ...


sqlite_vec = cast(SqliteVecModule, import_module("sqlite_vec"))


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


class HybridSearchIndex:
    """Experimental index with no ownership of original source documents."""

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
                content_hash TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(lexical);
            """
        )
        expected = {
            "schema_version": "2",
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

    def add(self, chunks: Sequence[TextChunk]) -> None:
        with self.connection:
            self._insert_chunks(chunks)

    def _insert_chunks(self, chunks: Sequence[TextChunk]) -> None:
        vectors = self.provider.embed_documents([chunk.text for chunk in chunks])
        for chunk, vector in zip(chunks, vectors, strict=True):
            cursor = self.connection.execute(
                """
                    INSERT INTO chunks (
                        chunk_id, source_id, text, char_start, char_end, page,
                        title_path, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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

    def replace_source(self, source_id: str, chunks: Sequence[TextChunk]) -> None:
        if any(chunk.source_id != source_id for chunk in chunks):
            raise ValueError("All replacement chunks must belong to the same source")
        vectors = self.provider.embed_documents([chunk.text for chunk in chunks])
        with self.connection:
            self._delete_source(source_id)
            for chunk, vector in zip(chunks, vectors, strict=True):
                cursor = self.connection.execute(
                    """
                    INSERT INTO chunks (
                        chunk_id, source_id, text, char_start, char_end, page,
                        title_path, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
    ) -> list[SearchResult]:
        lexical = self._lexical_ids(query, candidate_limit)
        rankings = [lexical]
        if not lexical_only:
            rankings.append(self._vector_ids(self.provider.embed_query(query), candidate_limit))
        fused = reciprocal_rank_fusion(rankings, k=rrf_k)[:limit]
        results: list[SearchResult] = []
        for chunk_id, score in fused:
            row = self.connection.execute(
                "SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)
            ).fetchone()
            if row is None:
                continue
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
                )
            )
        return results
