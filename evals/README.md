# LoreDock retrieval evaluations

This directory contains non-sensitive fixtures, model candidates and schemas for the Phase 1
retrieval experiments. Evaluation data must be safe to redistribute under the project license and
must not contain personal or production knowledge-base content.

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
