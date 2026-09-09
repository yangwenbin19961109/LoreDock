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


def test_semantic_markdown_keeps_table_code_and_faq_contexts_together() -> None:
    text = """# 常见问题

## 可以离线使用吗?

可以, 已经下载的资料无需联网。

# 配置

| 模型 | 维度 |
|---|---:|
| E5 | 384 |
| BGE-M3 | 1024 |

## 代码

```python
def answer() -> int:
    return 384
```
"""
    document = ParsedDocument("source", "semantic", text)
    hierarchy = chunk_document_hierarchy(
        document,
        ChunkingConfig(
            target_tokens=6,
            max_tokens=8,
            overlap_tokens=1,
            version=2,
            strategy="semantic_markdown",
        ),
    )

    assert {parent.kind for parent in hierarchy.parents} >= {"faq", "table", "code_scope"}
    assert all(
        document.text[chunk.char_start : chunk.char_end] == chunk.text for chunk in hierarchy.chunks
    )
    for parent in hierarchy.parents:
        assert document.text[parent.char_start : parent.char_end] == parent.text
    table_parent = next(parent for parent in hierarchy.parents if parent.kind == "table")
    assert "# 配置" in table_parent.text
    assert "模型 | 维度" in table_parent.text
    assert "BGE-M3 | 1024" in table_parent.text
    code_parent = next(parent for parent in hierarchy.parents if parent.kind == "code_scope")
    assert "## 代码" in code_parent.text
    assert "def answer" in code_parent.text
    generic = chunk_document_hierarchy(
        document,
        ChunkingConfig(
            target_tokens=6,
            max_tokens=8,
            overlap_tokens=1,
            strategy="generic",
        ),
    )
    assert [(chunk.char_start, chunk.char_end) for chunk in hierarchy.chunks] == [
        (chunk.char_start, chunk.char_end) for chunk in generic.chunks
    ]


def test_generic_strategy_remains_available_for_same_corpus_comparison() -> None:
    document = ParsedDocument("source", "test", "# Heading\n\n| A | B |\n|---|---|\n| 1 | 2 |")

    hierarchy = chunk_document_hierarchy(
        document,
        ChunkingConfig(target_tokens=32, max_tokens=32, overlap_tokens=0, strategy="generic"),
    )

    assert {parent.kind for parent in hierarchy.parents} == {"section"}
