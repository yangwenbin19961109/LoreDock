# ADR 0006: Authenticated desktop Core lifecycle

- Status: Accepted
- Date: 2026-09-02
- Decision owners: LoreDock project owner
- Supersedes: None
- Superseded by: None

## Context

The desktop application must start Core without a fixed port, must not expose an unauthenticated
local API to unrelated processes, and must close SQLite-backed services cleanly when the desktop
window exits. Browser-only development must continue to work through the Vite loopback proxy.

## Decision

Tauri owns the desktop Core child process. It selects an available `127.0.0.1` port, generates a
random per-process bearer token, passes both through environment variables, and waits for the
version handshake before exposing connection details through a narrow Tauri command. The Web API
adapter adds the token only when running inside Tauri; ordinary browser development retains its
relative `/api/v1` URLs.

Core requires the bearer token whenever `LOREDOCK_DESKTOP_TOKEN` is configured. A token-protected
desktop-only shutdown endpoint asks Uvicorn to finish gracefully. Tauri waits up to five seconds
and kills the owned child only as a last-resort fallback.

Tauri supervises the owned Core process after startup. Unexpected exits enter `recovering` and use
500 ms, 1 second, and 2 second delays before at most three automatic restarts. Exhausting that
budget enters `failed` and waits for an explicit user restart, which resets the budget. Normal
desktop shutdown never enters recovery. The WebView receives a redacted status contract separately
from the secret-bearing connection contract.

## Alternatives considered

- A fixed loopback port is simpler but conflicts with parallel instances and other local software.
- An unauthenticated random port reduces accidental collisions but does not prevent local process
  access after discovering the listener.
- Proxying every API request through Tauri IPC would avoid CORS and browser-held credentials, but
  duplicates the HTTP adapter and significantly expands desktop code.
- Terminating the process directly on every exit is simpler but can interrupt SQLite transactions.

## Consequences

- The token exists only for the lifetime of one desktop process and is never persisted.
- Recovery is bounded for the desktop process lifetime, preventing an infinite crash loop.
- Desktop WebViews require a narrowly scoped loopback CSP and Core CORS policy.
- Development locates the repository Python virtual environment; releases must package a
  platform-specific `core/loredock-core` executable as a Tauri resource.
- A narrow port-allocation race remains between releasing the probe socket and Uvicorn binding;
  startup failure is reported rather than silently switching to a fixed port.

## Validation

- Test that unauthenticated requests receive `desktop_auth_required`.
- Test the authenticated version and graceful-shutdown paths.
- Launch Tauri, verify the Core listener uses a dynamic loopback port, close the window, and verify
  both owned processes exit.
- Terminate a ready Core, verify a new process and port become ready, then verify repeated startup
  failures stop after the third automatic restart and can only resume through explicit recovery.
- Repeat lifecycle smoke tests on macOS and Linux after their packaged sidecars exist.
