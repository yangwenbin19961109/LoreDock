"""Rank fusion independent from storage and model implementations."""

from collections.abc import Iterable, Sequence


def reciprocal_rank_fusion(
    rankings: Iterable[Sequence[str]], *, k: int = 60
) -> list[tuple[str, float]]:
    if k <= 0:
        raise ValueError("RRF k must be positive")
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
