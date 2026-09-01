"""Deterministic local scale benchmark for the experimental index."""

import argparse
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path

from loredock.retrieval import HashingEmbeddingProvider, HybridSearchIndex, TextChunk


def percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * percentile_value), len(ordered) - 1)
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark LoreDock experimental retrieval")
    parser.add_argument("--chunks", type=int, default=10_000)
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    provider = HashingEmbeddingProvider()
    chunks = [
        TextChunk(
            id=f"chunk-{index}",
            source_id=f"source-{index // 10}",
            text=f"知识库基准资料 编号 {index} 主题 {index % 97} retrieval benchmark topic",
            char_start=0,
            char_end=48,
            page=None,
            title_path=("基准",),
            content_hash=f"hash-{index}",
        )
        for index in range(args.chunks)
    ]
    with tempfile.TemporaryDirectory(prefix="loredock-bench-") as directory:
        index_path = Path(directory) / "index.sqlite"
        started = time.perf_counter()
        with HybridSearchIndex(index_path, provider) as index:
            index.add(chunks)
            indexing_seconds = time.perf_counter() - started
            latencies: list[float] = []
            for query_index in range(args.queries):
                query_started = time.perf_counter()
                index.search(f"主题 {query_index % 97}", limit=10)
                latencies.append((time.perf_counter() - query_started) * 1000)
        report = {
            "system": platform.platform(),
            "python": platform.python_version(),
            "provider": provider.identifier,
            "dimensions": provider.dimensions,
            "chunks": args.chunks,
            "queries": args.queries,
            "indexing_seconds": indexing_seconds,
            "query_mean_ms": statistics.mean(latencies),
            "query_p95_ms": percentile(latencies, 0.95),
            "index_bytes": index_path.stat().st_size,
        }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
