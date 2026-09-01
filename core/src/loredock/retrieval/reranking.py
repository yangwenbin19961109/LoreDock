"""Optional reranker boundary; failures must preserve fused retrieval results."""

from collections.abc import Sequence
from typing import Protocol

from loredock.retrieval.index import SearchResult


class Reranker(Protocol):
    identifier: str

    def rerank(
        self, query: str, candidates: Sequence[SearchResult], *, limit: int
    ) -> list[SearchResult]: ...


def rerank_or_fallback(
    reranker: Reranker | None,
    query: str,
    candidates: Sequence[SearchResult],
    *,
    limit: int,
) -> list[SearchResult]:
    if reranker is None:
        return list(candidates[:limit])
    try:
        return reranker.rerank(query, candidates, limit=limit)
    except Exception:
        return list(candidates[:limit])
