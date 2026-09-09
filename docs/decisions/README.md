# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for significant LoreDock decisions.

Create a new record by copying `0000-template.md`, assigning the next four-digit number, and using a short kebab-case name, for example:

```text
0001-python-core.md
0002-per-library-sqlite-index.md
```

Accepted ADRs are immutable historical records. If a decision changes, add a new ADR that supersedes the earlier one.

Current accepted decisions include the Python Core sidecar boundary, its authenticated lifecycle,
per-library SQLite indexes, hybrid retrieval, authoritative original sources, hybrid Child retrieval with on-demand Parent
context, and managed consistent backups with restart-boundary restoration.
