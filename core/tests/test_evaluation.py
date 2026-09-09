from pathlib import Path
from typing import cast

from loredock.evaluation.metrics import calculate_metrics
from loredock.evaluation.runner import load_cases, run_evaluation
from loredock.ingestion.parsers import parse_path


def test_metrics_cover_recall_rank_and_citations() -> None:
    metrics = calculate_metrics(
        [{"a"}, {"c"}],
        [["a", "b"], ["b", "c"]],
        [[True, True], [True, False]],
        [[True, False], [False, True]],
        [[100, 200], [300, 400]],
        [["p1", "p2"], ["p3", "p3"]],
    )

    assert metrics.recall_at_k == 1.0
    assert metrics.first_result_accuracy == 0.5
    assert metrics.mean_reciprocal_rank == 0.75
    assert metrics.citation_accuracy == 0.75
    assert metrics.context_precision == 0.5
    assert metrics.expected_passage_coverage == 1.0
    assert metrics.average_context_chars == 250
    assert metrics.duplicate_context_rate == 0.25


def test_checked_in_evaluation_batch_has_unique_case_ids() -> None:
    cases_path = Path(__file__).resolve().parents[2] / "evals" / "fixtures" / "cases.json"
    cases = load_cases(cases_path)

    assert len(cases) == 200
    assert len({case["id"] for case in cases}) == len(cases)


def test_expected_passages_exist_in_an_expected_source() -> None:
    fixtures = Path(__file__).resolve().parents[2] / "evals" / "fixtures"
    cases = load_cases(fixtures / "cases.json")
    documents = {
        path.stem: parse_path(path).text
        for path in (fixtures / "documents").iterdir()
        if path.suffix.lower()
        in {".md", ".markdown", ".txt", ".pdf", ".docx", ".pptx", ".xlsx", ".htm", ".html"}
    }

    invalid_cases = [
        case["id"]
        for case in cases
        if case["expected_passages"]
        and not any(
            passage in documents.get(source_id, "")
            for source_id in case["expected_sources"]
            for passage in case["expected_passages"]
        )
    ]

    assert invalid_cases == []


def test_evaluation_records_reproducible_cost_metrics() -> None:
    fixtures = Path(__file__).resolve().parents[2] / "evals" / "fixtures"

    _, details = run_evaluation(fixtures / "documents", fixtures / "cases.json")

    index_build_seconds = cast(float, details["index_build_seconds"])
    index_bytes = cast(int, details["index_bytes"])
    query_p50_ms = cast(float, details["query_p50_ms"])
    query_p95_ms = cast(float, details["query_p95_ms"])
    assert index_build_seconds >= 0
    assert index_bytes > 0
    assert query_p50_ms >= 0
    assert query_p95_ms >= query_p50_ms
    tag_case_counts = cast(dict[str, int], details["tag_case_counts"])
    assert tag_case_counts["semantic-chunking"] == 21
    assert tag_case_counts["html"] == 9
    assert tag_case_counts["pptx"] == 4
    assert tag_case_counts["xlsx"] == 4
    assert tag_case_counts["cross-child"] == 13
    assert tag_case_counts["cross-lingual"] == 46
    assert tag_case_counts["citation-boundary"] == 17
    cases_detail = cast(list[dict[str, object]], details["cases_detail"])
    assert all("tags" in case for case in cases_detail)
