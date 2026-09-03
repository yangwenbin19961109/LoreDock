# LoreDock retrieval evaluations

This directory contains non-sensitive fixtures, model candidates and schemas for the Phase 1
retrieval experiments. Evaluation data must be safe to redistribute under the project license and
must not contain personal or production knowledge-base content.

The checked-in Phase 2.5 batch currently contains 14 documents and 100 reviewed questions covering
hierarchical prose, FAQ, tables, code, operations, security, PDF, DOCX, long documents and
cross-language retrieval. JSON
reports include per-case ranks and passage coverage so regressions can be diagnosed without
discarding difficult cases.

`cases.schema.json` defines the initial portable case format. Retrieval-affecting changes must run
the same versioned dataset and record model, device, vector dimensions, corpus size, and parameters.

Run the checked-in pilot set from the repository root:

```powershell
python -m uv run --directory core loredock-eval
python -m uv run --directory core loredock-eval --lexical-only
```

Run a disposable scale benchmark:

```powershell
python -m uv run --directory core loredock-bench --chunks 10000 --queries 100
```

The deterministic `loredock/hash-v1` provider verifies storage, fusion, metrics and fallback in CI.
It is not a semantic model and its scores must never be used to choose the production embedding
model. `models.toml` records the real model candidates for the separate ONNX comparison.

Install and verify the pinned E5 pilot package without adding model files to Git:

```powershell
python -m uv run --directory core loredock-model install-e5 --directory models/multilingual-e5-small
python -m uv run --directory core loredock-model smoke-e5 --directory models/multilingual-e5-small
python -m uv run --directory core loredock-eval --model-dir models/multilingual-e5-small
python -m uv run --directory core loredock-eval --model-dir models/multilingual-e5-small --vector-only
python -m uv run --directory core loredock-eval --model-dir models/multilingual-e5-small --context-strategy child
python -m uv run --directory core loredock-eval --model-dir models/multilingual-e5-small --context-strategy adjacent
```

Downloads are pinned to an immutable model revision and verified by size and SHA-256. Normal unit
tests remain offline and use fakes or `loredock/hash-v1`.
