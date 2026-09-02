"""Evaluation orchestration shared by CLI and tests."""

import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import TypedDict, cast

from loredock.evaluation.metrics import EvaluationMetrics, calculate_metrics
from loredock.ingestion import parse_path
from loredock.retrieval import (
    ChunkingConfig,
    ContextStrategy,
    EmbeddingProvider,
    HashingEmbeddingProvider,
    HybridSearchIndex,
)
from loredock.retrieval.chunking import chunk_document_hierarchy


class EvaluationCase(TypedDict):
    id: str
    query: str
    expected_sources: list[str]
    expected_passages: list[str]
    tags: list[str]


_DEFAULT_CONFIG = ChunkingConfig()


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array of strings")
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        raise ValueError(f"{field} must be an array of strings")
    return cast(list[str], items)


def load_cases(path: Path) -> list[EvaluationCase]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("Evaluation cases must be a JSON array")
    cases: list[EvaluationCase] = []
    for raw in cast(list[object], value):
        if not isinstance(raw, dict):
            raise ValueError("Each evaluation case must be an object")
        raw_map = cast(dict[str, object], raw)
        cases.append(
            EvaluationCase(
                id=str(raw_map["id"]),
                query=str(raw_map["query"]),
                expected_sources=_string_list(raw_map["expected_sources"], "expected_sources"),
                expected_passages=_string_list(
                    raw_map.get("expected_passages", []), "expected_passages"
                ),
                tags=_string_list(raw_map.get("tags", []), "tags"),
            )
        )
    return cases


def run_evaluation(
    documents_dir: Path,
    cases_path: Path,
    *,
    lexical_only: bool = False,
    limit: int = 10,
    config: ChunkingConfig = _DEFAULT_CONFIG,
    provider: EmbeddingProvider | None = None,
    context_strategy: ContextStrategy = "parent",
) -> tuple[EvaluationMetrics, dict[str, object]]:
    documents = [
        parse_path(path, source_id=path.stem)
        for path in sorted(documents_dir.iterdir())
        if path.suffix.lower() in {".md", ".markdown", ".txt", ".pdf", ".docx"}
    ]
    hierarchies = [chunk_document_hierarchy(document, config) for document in documents]
    chunks = [chunk for hierarchy in hierarchies for chunk in hierarchy.chunks]
    parents = [parent for hierarchy in hierarchies for parent in hierarchy.parents]
    active_provider = provider or HashingEmbeddingProvider()
    cases = load_cases(cases_path)
    expected: list[set[str]] = []
    retrieved: list[list[str]] = []
    citation_checks: list[list[bool]] = []
    context_relevance: list[list[bool]] = []
    context_lengths: list[list[int]] = []
    context_ids: list[list[str]] = []
    case_details: list[dict[str, object]] = []
    with (
        tempfile.TemporaryDirectory(prefix="loredock-eval-") as directory,
        HybridSearchIndex(Path(directory) / "index.sqlite", active_provider) as index,
    ):
        index.add(chunks, parents)
        for case in cases:
            results = index.search(
                case["query"],
                limit=limit,
                lexical_only=lexical_only,
                context_strategy=context_strategy,
            )
            expected.append(set(case["expected_sources"]))
            retrieved.append([result.source_id for result in results])
            citation_checks.append(
                [
                    0 <= result.char_start < result.char_end
                    and result.text
                    == next(
                        document.text[result.char_start : result.char_end]
                        for document in documents
                        if document.source_id == result.source_id
                    )
                    and result.context_text
                    == next(
                        document.text[
                            result.context_range.char_start : result.context_range.char_end
                        ]
                        for document in documents
                        if document.source_id == result.source_id
                    )
                    for result in results
                ]
            )
            context_relevance.append(
                [
                    result.source_id in case["expected_sources"]
                    and (
                        not case["expected_passages"]
                        or any(
                            passage in result.context_text for passage in case["expected_passages"]
                        )
                    )
                    for result in results
                ]
            )
            context_lengths.append([len(result.context_text) for result in results])
            context_ids.append([result.context_id for result in results])
            expected_sources = set(case["expected_sources"])
            first_relevant_rank = next(
                (
                    rank
                    for rank, result in enumerate(results, start=1)
                    if result.source_id in expected_sources
                ),
                None,
            )
            case_details.append(
                {
                    "id": case["id"],
                    "expected_sources": case["expected_sources"],
                    "retrieved_sources": [result.source_id for result in results],
                    "first_relevant_rank": first_relevant_rank,
                    "expected_passages_covered": [
                        passage
                        for passage in case["expected_passages"]
                        if any(passage in result.context_text for result in results)
                    ],
                }
            )
    metrics = calculate_metrics(
        expected,
        retrieved,
        citation_checks,
        context_relevance,
        context_lengths,
        context_ids,
    )
    details: dict[str, object] = {
        "metrics": asdict(metrics),
        "mode": "bm25" if lexical_only else "hybrid",
        "provider": active_provider.identifier,
        "dimensions": active_provider.dimensions,
        "documents": len(documents),
        "chunks": len(chunks),
        "chunking": asdict(config),
        "candidate_limit": 50,
        "rrf_k": 60,
        "result_limit": limit,
        "context_strategy": context_strategy,
        "cases_detail": case_details,
    }
    return metrics, details
