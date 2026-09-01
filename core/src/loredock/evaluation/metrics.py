"""Small dependency-free information retrieval metrics."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    cases: int
    recall_at_k: float
    first_result_accuracy: float
    mean_reciprocal_rank: float
    citation_accuracy: float


def calculate_metrics(
    expected: list[set[str]],
    retrieved: list[list[str]],
    citations_valid: list[list[bool]],
) -> EvaluationMetrics:
    if not expected or len(expected) != len(retrieved) or len(expected) != len(citations_valid):
        raise ValueError("Evaluation inputs must have the same non-zero length")
    recalls: list[float] = []
    first_hits = 0
    reciprocal_ranks: list[float] = []
    citation_values: list[bool] = []
    for relevant, ranking, valid in zip(expected, retrieved, citations_valid, strict=True):
        recalls.append(len(relevant.intersection(ranking)) / len(relevant))
        first_hits += int(bool(ranking) and ranking[0] in relevant)
        rank = next(
            (index for index, source in enumerate(ranking, start=1) if source in relevant), 0
        )
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        citation_values.extend(valid)
    return EvaluationMetrics(
        cases=len(expected),
        recall_at_k=sum(recalls) / len(recalls),
        first_result_accuracy=first_hits / len(expected),
        mean_reciprocal_rank=sum(reciprocal_ranks) / len(expected),
        citation_accuracy=(sum(citation_values) / len(citation_values) if citation_values else 1.0),
    )
