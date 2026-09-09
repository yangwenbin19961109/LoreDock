"""Deterministic local scale benchmark for the experimental index."""

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

from loredock.retrieval import (
    EmbeddingProvider,
    HashingEmbeddingProvider,
    HybridSearchIndex,
    TextChunk,
)
from loredock.retrieval.model_assets import load_e5_provider


def percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * percentile_value), len(ordered) - 1)
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark LoreDock experimental retrieval")
    parser.add_argument("--chunks", type=int, default=10_000)
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        help="Maximum number of documents embedded per index write.",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Write batch progress and Python memory diagnostics to stderr.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--model-dir",
        type=Path,
        help="Use an already verified local multilingual-e5-small package instead of hashing.",
    )
    args = parser.parse_args()
    if args.chunks < 1 or args.queries < 1 or args.batch_size < 1:
        parser.error("--chunks, --queries, and --batch-size must be positive")
    provider: EmbeddingProvider = (
        load_e5_provider(args.model_dir)
        if args.model_dir is not None
        else HashingEmbeddingProvider()
    )
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
    if args.progress:
        tracemalloc.start()

    def report_progress(stage: str, completed: int) -> None:
        if not args.progress:
            return
        current, peak = tracemalloc.get_traced_memory()
        print(
            f"benchmark stage={stage} completed={completed}/{args.chunks} "
            f"python_current_mib={current / 1024 / 1024:.1f} "
            f"python_peak_mib={peak / 1024 / 1024:.1f}",
            file=sys.stderr,
            flush=True,
        )

    with tempfile.TemporaryDirectory(prefix="loredock-bench-") as directory:
        index_path = Path(directory) / "index.sqlite"
        started = time.perf_counter()
        with HybridSearchIndex(index_path, provider) as index:
            for start in range(0, len(chunks), args.batch_size):
                index.add(chunks[start : start + args.batch_size])
                report_progress("indexing", min(start + args.batch_size, len(chunks)))
            indexing_seconds = time.perf_counter() - started
            latencies: list[float] = []
            for query_index in range(args.queries):
                query_started = time.perf_counter()
                index.search(f"主题 {query_index % 97}", limit=10)
                latencies.append((time.perf_counter() - query_started) * 1000)
            report_progress("querying", args.chunks)
        report = {
            "system": platform.platform(),
            "python": platform.python_version(),
            "provider": provider.identifier,
            "dimensions": provider.dimensions,
            "chunks": args.chunks,
            "queries": args.queries,
            "indexing_seconds": indexing_seconds,
            "query_mean_ms": statistics.mean(latencies),
            "query_p50_ms": percentile(latencies, 0.5),
            "query_p95_ms": percentile(latencies, 0.95),
            "index_bytes": index_path.stat().st_size,
        }
    if args.progress:
        tracemalloc.stop()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
