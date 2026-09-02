from loredock.ingestion.parsers import ParsedDocument
from loredock.retrieval.chunking import (
    ChunkingConfig,
    chunk_document,
    chunk_document_hierarchy,
)


def test_chunks_preserve_offsets_and_heading_path() -> None:
    text = "# 标题\n\n第一段用于测试。\n\n## 子标题\n\n第二段继续测试。"
    document = ParsedDocument("source", "测试", text)

    chunks = chunk_document(
        document, ChunkingConfig(target_tokens=8, max_tokens=12, overlap_tokens=2)
    )

    assert len(chunks) >= 2
    assert all(text[chunk.char_start : chunk.char_end] == chunk.text for chunk in chunks)
    assert chunks[0].title_path == ("标题",)
    assert chunks[-1].title_path == ("标题", "子标题")


def test_chunk_ids_are_deterministic() -> None:
    document = ParsedDocument("source", "test", "alpha beta gamma delta")
    config = ChunkingConfig(target_tokens=2, max_tokens=3, overlap_tokens=1)

    first = chunk_document(document, config)
    second = chunk_document(document, config)

    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]


def test_hierarchy_links_children_to_stable_sections() -> None:
    text = "# Alpha\n\n" + "alpha detail " * 12 + "\n\n# Beta\n\n" + "beta detail " * 12
    document = ParsedDocument("source", "test", text)
    config = ChunkingConfig(target_tokens=6, max_tokens=8, overlap_tokens=1)

    first = chunk_document_hierarchy(document, config)
    second = chunk_document_hierarchy(document, config)

    assert len(first.parents) == 2
    assert [parent.id for parent in first.parents] == [parent.id for parent in second.parents]
    assert all(chunk.parent_id is not None for chunk in first.chunks)
    assert first.chunks[0].previous_id is None
    assert first.chunks[-1].next_id is None
    assert all(
        chunk.next_id == first.chunks[index + 1].id for index, chunk in enumerate(first.chunks[:-1])
    )
