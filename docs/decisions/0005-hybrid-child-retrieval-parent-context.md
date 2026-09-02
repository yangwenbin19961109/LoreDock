# ADR 0005: Hybrid child retrieval with on-demand parent context

- Status: Accepted
- Date: 2026-09-02
- Decision owners: LoreDock maintainers
- Supersedes: None
- Superseded by: None

## Context

LoreDock already combines FTS5 and vector candidates with reciprocal rank fusion. Small chunks improve retrieval precision and citation accuracy, but a single matching chunk can omit the heading, prerequisite, continuation, table boundary, or code scope needed by a person or Agent. Indexing and returning whole files would add unrelated text, consume excessive context, and weaken precise citations.

Hybrid retrieval and parent-child retrieval address different dimensions: the former chooses relevant candidates, while the latter controls the context returned around a match.

## Decision

LoreDock will keep Child chunks as the primary lexical and vector ranking units. Rebuildable Parent nodes will represent meaningful sections such as headings, page groups, tables, code scopes, question-answer units, or conversation windows.

After BM25 and vector candidates are fused, the search pipeline will deduplicate and group Child hits, then selectively return the matched Child, adjacent Children, a continuous range, or the Parent according to document structure and a bounded context budget.

The ranking match and returned context remain separate in public contracts. Results retain both `matched_range` and `context_range`, so clients can highlight the actual hit while reading a larger context. Whole-file parent vectors are not part of the default design.

Short notes and naturally complete units may omit a separate Parent. MCP search remains compact and returns handles for bounded follow-up reads.

## Alternatives considered

- **Hybrid retrieval over flat chunks only:** simpler, but often returns fragmented context.
- **Parent-only retrieval:** provides complete sections but reduces location precision and can blur multiple topics.
- **Child retrieval that always returns the full Parent:** predictable but wastes tokens and introduces unrelated content.
- **Whole-file vectors:** easy to model but unsuitable for long, multi-topic sources and precise citations.

## Consequences

- Index schema gains Parent records and Child `parent_id`, `ordinal`, `previous_id`, and `next_id` fields.
- Implementing the decision requires a new index build-contract version and a rebuild of derived indexes; original sources and application metadata remain compatible.
- Search responses gain additive matched-versus-context fields before MCP contracts are frozen.
- Parsers and chunkers require document-type-specific Parent construction.
- Retrieval adds grouping, expansion, context budgeting, and duplicate suppression, increasing implementation and test complexity.
- The design improves contextual completeness without sacrificing Child-level citations or BM25-only fallback.

## Validation

- Compare flat Child retrieval, adjacent-Child expansion, and Parent expansion on the same versioned evaluation set.
- Record Recall@K, MRR, citation accuracy, context precision, duplicate rate, average returned tokens, P95 latency, and index size.
- Include Markdown, PDF, DOCX, tables, code, FAQ, short notes, and long multi-topic sources.
- Verify that BM25-only mode uses the same grouping and bounded expansion rules.
- Verify migration by rebuilding a version-2 index into the new contract without modifying original source files.
