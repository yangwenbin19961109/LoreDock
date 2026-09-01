# ADR 0004: Source material is authoritative

- Status: Accepted
- Date: 2026-09-01
- Decision owners: LoreDock project owner
- Supersedes: None
- Superseded by: None

## Context

Users must be able to inspect, export, migrate, and recover their knowledge without depending on a
specific embedding model, vector extension, or LoreDock release.

## Decision

Original files, notes, and captured URL snapshots are the source of truth. Parsed artifacts,
chunks, FTS data, and vectors are derived and rebuildable. Stable source and chunk references must
retain enough provenance to open the source context after retrieval.

## Alternatives considered

- Keeping only extracted text would lose fidelity and make reparsing impossible.
- Treating vectors as primary data would lock users to an embedding contract.

## Consequences

- Import and deletion must manage raw copies explicitly.
- Backups prioritize sources, application metadata, and build manifests.
- Index schema changes can prefer deterministic rebuilds over complex in-place migrations.

## Validation

- Delete and recreate every derived artifact from a backup containing only authoritative data and
  manifests, then verify citations and search quality.
