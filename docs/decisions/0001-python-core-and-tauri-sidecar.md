# ADR 0001: Python Core and Tauri desktop sidecar

- Status: Accepted
- Date: 2026-09-01
- Decision owners: LoreDock project owner
- Supersedes: None
- Superseded by: None

## Context

LoreDock needs one knowledge-processing core for desktop and server editions. Python has the
strongest document-processing and inference ecosystem, while the desktop application must remain
smaller than a typical Electron application and must not require a system Python installation.

## Decision

Use Python 3.12, FastAPI, and Pydantic for LoreDock Core. Use Tauri 2 as the desktop shell. Desktop
releases package Core as a platform-specific sidecar and communicate with it through a versioned
loopback HTTP API. Local Core binds to a loopback address only.

## Alternatives considered

- A Rust-only Core would simplify native packaging but increase model and parser integration work.
- Electron would simplify process management but increase application size and baseline memory.
- A Python webview shell would reduce language count but provide a weaker desktop platform layer.

## Consequences

- Python and Rust build pipelines must be maintained.
- The desktop process needs explicit sidecar lifecycle, dynamic port, health, and version handling.
- Server and desktop editions can share application use cases and HTTP contracts.
- End users do not need to install Python.

## Validation

- Build and launch the packaged sidecar on Windows, macOS, and Linux.
- Verify graceful shutdown, crash recovery, version mismatch handling, and loopback-only binding.
