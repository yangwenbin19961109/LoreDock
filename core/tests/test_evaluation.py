from loredock.evaluation.metrics import calculate_metrics


def test_metrics_cover_recall_rank_and_citations() -> None:
    metrics = calculate_metrics(
        [{"a"}, {"c"}],
        [["a", "b"], ["b", "c"]],
        [[True, True], [True, False]],
    )

    assert metrics.recall_at_k == 1.0
    assert metrics.first_result_accuracy == 0.5
    assert metrics.mean_reciprocal_rank == 0.75
    assert metrics.citation_accuracy == 0.75
