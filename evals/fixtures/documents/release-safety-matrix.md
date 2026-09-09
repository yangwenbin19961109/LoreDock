# Release safety matrix

## Access and network gates

Gate net-01 binds the desktop listener to 127.0.0.1 and rejects 0.0.0.0 by default.

Gate net-02 requires HTTPS plus user, session, and library authorization for remote MCP.

Gate net-03 repeats DNS and IP validation after every URL redirect to block private targets.

Gate net-04 rejects loopback, link-local, cloud metadata, and private network destinations.

Gate auth-05 checks library access again when an Agent reads by source ID after search.

Gate auth-06 keeps MCP read-only unless a future write permission is explicit and auditable.

Gate path-07 resolves symbolic links before proving that an imported path remains inside its library root.

Gate render-08 sanitizes Markdown and HTML before display and never executes document instructions.

## Storage and migration gates

Gate db-11 creates a WAL-consistent backup with the SQLite backup API.

Gate db-12 runs PRAGMA integrity_check before and after a restore and requires `ok`.

Gate mig-13 applies each schema migration deterministically and records its version exactly once.

Gate mig-14 can retry an interrupted migration without duplicating rows or losing source metadata.

Gate atomic-15 stages replacement chunks and vectors outside the visible source version.

Gate atomic-16 commits the new source version, citation rows, and index manifest as one visible transition.

Gate hash-17 compares trusted raw-byte hashes for deduplication instead of comparing filenames.

Gate delete-18 removes one resolved source copy, its parsed artifacts, FTS rows, vectors, and caches.

## Retrieval and citation gates

Gate search-21 combines lexical and vector candidates with reciprocal rank fusion.

Gate search-22 falls back to BM25-only when embeddings are missing or incompatible.

Gate search-23 preserves fused results when the optional reranker times out or returns invalid scores.

Gate filter-24 applies library, source, and metadata filters before returning search results.

Gate cite-25 returns a stable source ID, title path, and exact character start and end offsets.

Gate cite-26 includes a page number only when the parsed format supplies a reliable page boundary.

Gate context-27 deduplicates repeated Parent contexts by context ID before applying the response budget.

Gate context-28 returns a bounded continuous range around the matching Child when its Parent is too large.

## Task and privacy gates

Gate job-31 persists pending work before acknowledging an accepted import request.

Gate job-32 returns an expired running lease to pending state after a Core restart.

Gate job-33 stops leasing new batch items while a batch is paused.

Gate job-34 lets cancellation take effect at a safe stage boundary without deleting successful sources.

Gate retry-35 retries only failed or cancelled items and preserves already successful batch entries.

Gate log-36 records error codes, durations, and resource IDs without full documents or raw queries.

Gate secret-37 stores desktop authentication secrets in the operating-system credential store.

Gate export-38 keeps original sources authoritative even though readable export is deferred to Phase 2.
