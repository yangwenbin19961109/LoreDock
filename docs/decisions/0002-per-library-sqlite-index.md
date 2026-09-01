# ADR 0002: Per-library SQLite indexes

- Status: Accepted
- Date: 2026-09-01
- Decision owners: LoreDock project owner
- Supersedes: None
- Superseded by: None

## Context

LoreDock is local-first and must work without a separately managed database. User-facing metadata
has a different lifecycle from rebuildable chunks, FTS rows, and vectors. Libraries also need
simple isolation, deletion, backup, and reindex behavior.

## Decision

Store application metadata in `app.sqlite`. Store each library's rebuildable search projection in
`libraries/{library_id}/index.sqlite`, alongside its `raw/`, `artifacts/`, and `manifest.json`.
Use WAL mode during normal operation. Treat raw sources and snapshots as authoritative; indexes are
derived artifacts that may be deleted and rebuilt.

## Alternatives considered

- One SQLite database would simplify transactions but couple authoritative and rebuildable data.
- PostgreSQL would support concurrency but violate zero-service local installation.
- A vector database as the primary store would make export and source lifecycle harder to reason about.

## Consequences

- Cross-database operations cannot rely on one SQLite transaction and require durable, idempotent jobs.
- Per-library operations and scans have a natural scope.
- Active databases must be backed up with the SQLite backup API or a WAL-consistent snapshot.

## Validation

- Test atomic single-source rebuild, deletion, crash recovery, backup, restore, and index recreation.
