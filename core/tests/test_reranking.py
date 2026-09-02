from loredock.retrieval.index import CitationRange, SearchResult
from loredock.retrieval.reranking import rerank_or_fallback


class BrokenReranker:
    identifier = "broken"

    def rerank(self, *_args: object, **_kwargs: object) -> list[SearchResult]:
        raise RuntimeError("model unavailable")


def test_reranker_failure_returns_fused_candidates() -> None:
    location = CitationRange(0, 4, None, None)
    candidate = SearchResult(
        "c", "s", "text", 1.0, 0, 4, None, (), "c", None, "c", "text", location, location
    )

    assert rerank_or_fallback(BrokenReranker(), "query", [candidate], limit=1) == [candidate]
