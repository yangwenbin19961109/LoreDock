# Contributing to LoreDock

Thank you for helping build LoreDock. The project is at an early stage, so proposals that simplify the product and preserve local-first operation are especially valuable.

LoreDock is source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). By submitting a contribution, you confirm that you have the right to submit it and agree that it may be distributed under the project's current license. Do not submit third-party code whose license is incompatible with these terms.

## Before contributing

1. Read [the technical architecture](docs/technical-architecture.md).
2. Read [the agent and repository constraints](AGENTS.md).
3. Check whether the change affects persisted data, MCP contracts, security, packaging, or retrieval quality.
4. Discuss large architectural changes before implementing them.

## Pull requests

- Keep each pull request focused on one coherent outcome.
- Explain user-visible behavior and important tradeoffs.
- Include tests for new behavior and regressions.
- Update documentation when APIs, configuration, storage, or workflows change.
- Do not include credentials, private knowledge-base data, generated model files, local databases, or unrelated formatting changes.
- State which checks were run and identify anything that could not be verified.

## Commit messages

Use concise Conventional Commit-style subjects when practical:

```text
feat(search): add reciprocal rank fusion
fix(index): recover interrupted source replacement
docs(mcp): document read-only tool contract
```

Common types are `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, and `chore`.

## Architecture decisions

Cross-cutting or difficult-to-reverse decisions require an ADR created from `docs/decisions/0000-template.md`. Examples include replacing SQLite, changing the desktop framework, adopting a new MCP transport, or changing the index build contract.

## Security reports

Do not open a public issue containing secrets, private user content, or a working exploit. A private reporting channel will be documented before the first public release.
