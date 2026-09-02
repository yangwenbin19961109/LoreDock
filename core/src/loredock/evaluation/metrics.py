"""Small dependency-free information retrieval metrics."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    cases: int
    recall_at_k: float
    first_result_accuracy: float
    mean_reciprocal_rank: float
    citation_accuracy: float
    context_precision: float
    expected_passage_coverage: float
    average_context_chars: float
    duplicate_context_rate: float


def calculate_metrics(
    expected: list[set[str]],
    retrieved: list[list[str]],
    citations_valid: list[list[bool]],
    context_relevant: list[list[bool]] | None = None,
    context_lengths: list[list[int]] | None = None,
    context_ids: list[list[str]] | None = None,
) -> EvaluationMetrics:
    if not expected or len(expected) != len(retrieved) or len(expected) != len(citations_valid):
        raise ValueError("Evaluation inputs must have the same non-zero length")
    recalls: list[float] = []
    first_hits = 0
    reciprocal_ranks: list[float] = []
    citation_values: list[bool] = []
    context_values: list[bool] = []
    context_case_hits = 0
    lengths: list[int] = []
    duplicate_count = 0
    context_count = 0
    for case_index, (relevant, ranking, valid) in enumerate(
        zip(expected, retrieved, citations_valid, strict=True)
    ):
        recalls.append(len(relevant.intersection(ranking)) / len(relevant))
        first_hits += int(bool(ranking) and ranking[0] in relevant)
        rank = next(
            (index for index, source in enumerate(ranking, start=1) if source in relevant), 0
        )
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        citation_values.extend(valid)
        if context_relevant is not None:
            case_context = context_relevant[case_index]
            context_values.extend(case_context)
            context_case_hits += int(any(case_context))
        if context_lengths is not None:
            lengths.extend(context_lengths[case_index])
        if context_ids is not None:
            ids = context_ids[case_index]
            context_count += len(ids)
            duplicate_count += len(ids) - len(set(ids))
    return EvaluationMetrics(
        cases=len(expected),
        recall_at_k=sum(recalls) / len(recalls),
        first_result_accuracy=first_hits / len(expected),
        mean_reciprocal_rank=sum(reciprocal_ranks) / len(expected),
        citation_accuracy=(sum(citation_values) / len(citation_values) if citation_values else 1.0),
        context_precision=(sum(context_values) / len(context_values) if context_values else 1.0),
        expected_passage_coverage=(
            context_case_hits / len(expected) if context_relevant is not None else 1.0
        ),
        average_context_chars=(sum(lengths) / len(lengths) if lengths else 0.0),
        duplicate_context_rate=(duplicate_count / context_count if context_count else 0.0),
    )
