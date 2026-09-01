"""Evaluation orchestration shared by CLI and tests."""

import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import TypedDict, cast

from loredock.evaluation.metrics import EvaluationMetrics, calculate_metrics
from loredock.ingestion import parse_path
from loredock.retrieval import ChunkingConfig, HashingEmbeddingProvider, HybridSearchIndex
from loredock.retrieval.chunking import chunk_document


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
) -> tuple[EvaluationMetrics, dict[str, object]]:
    documents = [
        parse_path(path, source_id=path.stem)
        for path in sorted(documents_dir.iterdir())
        if path.suffix.lower() in {".md", ".markdown", ".txt", ".pdf", ".docx"}
    ]
    chunks = [chunk for document in documents for chunk in chunk_document(document, config)]
    provider = HashingEmbeddingProvider()
    cases = load_cases(cases_path)
    expected: list[set[str]] = []
    retrieved: list[list[str]] = []
    citation_checks: list[list[bool]] = []
    with (
        tempfile.TemporaryDirectory(prefix="loredock-eval-") as directory,
        HybridSearchIndex(Path(directory) / "index.sqlite", provider) as index,
    ):
        index.add(chunks)
        for case in cases:
            results = index.search(case["query"], limit=limit, lexical_only=lexical_only)
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
                    for result in results
                ]
            )
    metrics = calculate_metrics(expected, retrieved, citation_checks)
    details: dict[str, object] = {
        "metrics": asdict(metrics),
        "mode": "bm25" if lexical_only else "hybrid",
        "provider": provider.identifier,
        "dimensions": provider.dimensions,
        "documents": len(documents),
        "chunks": len(chunks),
        "chunking": asdict(config),
        "candidate_limit": 50,
        "rrf_k": 60,
        "result_limit": limit,
    }
    return metrics, details
