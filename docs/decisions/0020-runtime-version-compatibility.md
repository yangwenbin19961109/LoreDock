# ADR 0020: Runtime version compatibility and migration boundaries

- Status: Accepted
- Date: 2026-09-09
- Decision owners: LoreDock project owner
- Supersedes: None
- Superseded by: None

## Context

LoreDock already migrates `app.sqlite` sequentially and rebuilds each library index when its build contract changes. Schema versions were duplicated across modules, and the desktop handshake checked only the API version.

## Decision

Keep application schema and index schema versions beside the Core and API version constants. The version endpoint reports all four values. The bundled desktop accepts only the Core, API, application schema, and index schema versions it was built for.

Application metadata migrates forward in deterministic transactions. A database created by a newer LoreDock version is rejected before journal settings or schema changes are applied. Rebuildable indexes are not migrated in place: LoreDock rebuilds an incompatible index beside the active file, validates it through normal construction, and switches it atomically.

## Alternatives considered

Allowing any Core patch version would make mixed desktop/Core installations harder to diagnose. In-place index migrations would add recovery complexity even though original sources remain authoritative.

## Consequences

A mismatched installation stops with an actionable compatibility error instead of continuing with an untested combination. Releasing a schema or index-contract change requires updating one Core constant and the desktop expectations together. Users must run a matched desktop/Core bundle.

## Validation

Tests cover retry-safe application migration, preservation of existing metadata, rejection of future schemas, rebuilding an old index contract without changing its source, the expanded version response, and desktop rejection of mismatched versions.
