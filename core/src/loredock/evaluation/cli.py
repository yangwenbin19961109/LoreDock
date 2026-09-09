"""Command line entry point for the checked-in retrieval evaluation."""

import argparse
import json
from pathlib import Path
from typing import cast

from loredock.evaluation.runner import run_evaluation
from loredock.retrieval import ChunkingConfig, ChunkingStrategy, ContextStrategy
from loredock.retrieval.model_assets import load_e5_provider

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LoreDock retrieval evaluation")
    parser.add_argument(
        "--documents", type=Path, default=_REPOSITORY_ROOT / "evals/fixtures/documents"
    )
    parser.add_argument(
        "--cases", type=Path, default=_REPOSITORY_ROOT / "evals/fixtures/cases.json"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lexical-only", action="store_true")
    parser.add_argument("--vector-only", action="store_true")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument(
        "--context-strategy", choices=("child", "adjacent", "parent"), default="parent"
    )
    parser.add_argument(
        "--chunking-strategy",
        choices=("generic", "semantic_markdown"),
        default="generic",
        help="Select the Parent/Child construction strategy for a controlled evaluation run.",
    )
    args = parser.parse_args()
    if args.lexical_only and args.vector_only:
        parser.error("--lexical-only and --vector-only cannot be used together")
    provider = load_e5_provider(args.model_dir) if args.model_dir is not None else None
    chunking_strategy = cast(ChunkingStrategy, args.chunking_strategy)
    _, details = run_evaluation(
        args.documents,
        args.cases,
        lexical_only=args.lexical_only,
        vector_only=args.vector_only,
        provider=provider,
        context_strategy=cast(ContextStrategy, args.context_strategy),
        config=ChunkingConfig(
            version=2 if chunking_strategy == "semantic_markdown" else 1,
            strategy=chunking_strategy,
        ),
    )
    rendered = json.dumps(details, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
