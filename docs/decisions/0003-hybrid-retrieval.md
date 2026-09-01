# ADR 0003: FTS5, sqlite-vec, and reciprocal rank fusion

- Status: Accepted
- Date: 2026-09-01
- Decision owners: LoreDock project owner
- Supersedes: None
- Superseded by: None

## Context

Lexical search is strong for exact names, model numbers, and code, while vector search handles
semantic variation. LoreDock must continue searching when local or remote embedding models are
unavailable. SQLite remains the default local data engine.

## Decision

Use SQLite FTS5 for lexical retrieval and sqlite-vec behind a `VectorIndex` adapter for vector
retrieval. Fuse ranked candidates with reciprocal rank fusion. Reranking is optional and must
degrade to fused results on failure. BM25-only search is a supported runtime mode.

Initial candidate counts and weights are experimental values owned by the Phase 1 evaluation, not
permanent product constants.

## Alternatives considered

- Vector-only retrieval would weaken exact lookup and remove the offline degradation path.
- Score normalization would couple fusion to provider-specific score distributions.
- A required Qdrant service would increase local installation complexity.

## Consequences

- Search code must keep lexical and vector lanes independently testable.
- sqlite-vec-specific SQL and types stay inside the adapter.
- Retrieval changes require evaluation against a stable dataset.

## Validation

- Measure Recall@K, MRR, nDCG, citation accuracy, latency, memory, and index size at target scales.
