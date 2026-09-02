from pathlib import Path

from loredock.ingestion.parsers import ParsedDocument
from loredock.retrieval import HashingEmbeddingProvider, HybridSearchIndex
from loredock.retrieval.analyzer import lexical_terms
from loredock.retrieval.chunking import (
    ChunkingConfig,
    chunk_document,
    chunk_document_hierarchy,
)
from loredock.retrieval.fusion import reciprocal_rank_fusion


def test_chinese_analyzer_adds_bigrams() -> None:
    assert "知识" in lexical_terms("知识库")
    assert "识库" in lexical_terms("知识库")


def test_rrf_is_deterministic() -> None:
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]], k=60)

    assert fused[0][0] == "b"
    assert {item for item, _ in fused} == {"a", "b", "c"}


def test_hybrid_and_lexical_fallback_return_citations(tmp_path: Path) -> None:
    document = ParsedDocument("hybrid", "混合检索", "向量不可用时使用 BM25 only 全文检索。")
    chunks = chunk_document(
        document, ChunkingConfig(target_tokens=64, max_tokens=64, overlap_tokens=0)
    )
    with HybridSearchIndex(tmp_path / "index.sqlite", HashingEmbeddingProvider(32)) as index:
        index.add(chunks)

        hybrid = index.search("BM25 全文检索")
        fallback = index.search("BM25 全文检索", lexical_only=True)

    assert hybrid[0].source_id == "hybrid"
    assert fallback[0].source_id == "hybrid"
    assert document.text[hybrid[0].char_start : hybrid[0].char_end] == hybrid[0].text


def test_index_rejects_embedding_contract_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "index.sqlite"
    with HybridSearchIndex(path, HashingEmbeddingProvider(32)):
        pass

    try:
        HybridSearchIndex(path, HashingEmbeddingProvider(64))
    except ValueError as error:
        assert "build contract" in str(error)
    else:
        raise AssertionError("Expected mismatched vector dimensions to be rejected")


def test_source_replacement_is_atomic_and_removes_old_terms(tmp_path: Path) -> None:
    config = ChunkingConfig(target_tokens=64, max_tokens=64, overlap_tokens=0)
    old_chunks = chunk_document(ParsedDocument("source", "old", "obsolete keyword"), config)
    new_chunks = chunk_document(ParsedDocument("source", "new", "current keyword"), config)
    with HybridSearchIndex(tmp_path / "index.sqlite", HashingEmbeddingProvider(32)) as index:
        index.replace_source("source", old_chunks)
        index.replace_source("source", new_chunks)

        assert index.search("obsolete", lexical_only=True) == []
        assert index.search("current", lexical_only=True)[0].text == "current keyword"


def test_child_match_returns_bounded_parent_context(tmp_path: Path) -> None:
    text = "# Retrieval\n\n" + "background " * 20 + "needle fact " + "continuation " * 20
    hierarchy = chunk_document_hierarchy(
        ParsedDocument("source", "retrieval", text),
        ChunkingConfig(target_tokens=8, max_tokens=8, overlap_tokens=0),
    )
    with HybridSearchIndex(tmp_path / "index.sqlite", HashingEmbeddingProvider(32)) as index:
        index.add(hierarchy.chunks, hierarchy.parents)
        result = index.search("needle", lexical_only=True, max_context_chars=80)[0]

    assert result.matched_chunk_id == result.chunk_id
    assert result.parent_id is not None
    assert "needle" in result.text
    assert "needle" in result.context_text
    assert len(result.context_text) <= 80
    assert result.context_range.char_start <= result.matched_range.char_start
    assert result.context_range.char_end >= result.matched_range.char_end


def test_results_with_same_parent_are_grouped(tmp_path: Path) -> None:
    text = "# One\n\nkeyword first.\n\nkeyword second.\n\n# Two\n\nkeyword third."
    hierarchy = chunk_document_hierarchy(
        ParsedDocument("source", "grouping", text),
        ChunkingConfig(target_tokens=4, max_tokens=4, overlap_tokens=0),
    )
    with HybridSearchIndex(tmp_path / "index.sqlite", HashingEmbeddingProvider(32)) as index:
        index.add(hierarchy.chunks, hierarchy.parents)
        results = index.search("keyword", lexical_only=True, limit=8)

    assert len({result.context_id for result in results}) == len(results)
    assert len(results) == 2


def test_context_strategies_keep_the_same_ranked_child(tmp_path: Path) -> None:
    text = "# Section\n\n" + "alpha " * 12 + "needle answer " + "omega " * 12
    hierarchy = chunk_document_hierarchy(
        ParsedDocument("source", "strategies", text),
        ChunkingConfig(target_tokens=6, max_tokens=6, overlap_tokens=0),
    )
    with HybridSearchIndex(tmp_path / "index.sqlite", HashingEmbeddingProvider(32)) as index:
        index.add(hierarchy.chunks, hierarchy.parents)
        child = index.search("needle", lexical_only=True, context_strategy="child")[0]
        adjacent = index.search("needle", lexical_only=True, context_strategy="adjacent")[0]
        parent = index.search("needle", lexical_only=True, context_strategy="parent")[0]

    assert child.matched_chunk_id == adjacent.matched_chunk_id == parent.matched_chunk_id
    assert child.context_text == child.text
    assert len(child.context_text) <= len(adjacent.context_text) <= len(parent.context_text)
    assert "needle" in adjacent.context_text
