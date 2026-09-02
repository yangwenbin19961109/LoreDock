"""Install and validate the pinned default local embedding model."""

import argparse
from pathlib import Path

from loredock.retrieval.model_assets import install_e5_package, load_e5_provider


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage LoreDock local model assets")
    parser.add_argument("command", choices=("install-e5", "verify-e5", "smoke-e5"))
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "install-e5":
        install_e5_package(args.directory, progress=print)
    provider = load_e5_provider(args.directory)
    if args.command == "smoke-e5":
        query = provider.embed_query("知识库如何进行混合检索?")
        documents = provider.embed_documents(
            ["混合检索结合全文索引和向量召回。", "今天的天气很好。"]
        )
        scores = [
            sum(left * right for left, right in zip(query, item, strict=True)) for item in documents
        ]
        if scores[0] <= scores[1]:
            raise RuntimeError("E5 smoke retrieval did not rank the relevant passage first")
        print(f"E5 smoke test passed: relevant={scores[0]:.4f}, unrelated={scores[1]:.4f}")
    else:
        print(f"E5 package verified: {provider.identifier}")


if __name__ == "__main__":
    main()
