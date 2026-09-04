# ADR 0011: SDK-based local stdio bridge

- Status: Accepted
- Date: 2026-09-04
- Decision owners: LoreDock maintainers

## Decision

Use the official Python MCP SDK maintenance line (`mcp>=1.28,<2`, locked to 1.29.1), with the low-level server API so the existing six request schemas remain authoritative. v2 is a separate future upgrade requiring protocol regression tests. References: [official SDK](https://github.com/modelcontextprotocol/python-sdk), [v1 documentation](https://py.sdk.modelcontextprotocol.io/v1/).

The bridge is an independent stdio process. It calls only the Core read endpoint, never opens SQLite or starts a second Core. Production HTTP clients disable environment proxies and redirects, accept only numeric loopback HTTP addresses with explicit ports, use a 30-second timeout and cap responses at 512 KiB. Unknown tools and invalid arguments are rejected before forwarding. Tool errors use `isError` and stable structured error codes; raw HTTP errors and private validation input are not returned.

## Dependency and distribution considerations

The SDK is MIT licensed and supports Python on the target platforms; retain its license notice when redistributing. `httpx` (BSD-3-Clause) becomes a direct runtime dependency. The lock file adds transitive dependencies including cryptography and Windows-only pywin32; no optional SDK CLI or model framework is added. This changes the packaging dependency surface: standalone bridge size, license-notice assembly and macOS/Linux binaries must be checked before distribution. No installer or new standalone executable is claimed by this increment.

## Limits and follow-up

Development startup uses `python -m loredock.mcp.bridge` or `loredock-mcp`, with `LOREDOCK_BRIDGE_URL` and `LOREDOCK_BRIDGE_TOKEN` supplied by the launching environment. The token must be a read grant, never the desktop owner token. Do not commit real credentials or write them into example configuration. Environment injection is a development boundary, not a replacement for the planned OS credential store.

Core restart changes its dynamic address and invalidates in-memory grants; the bridge returns an actionable connection or authentication error. Automatic rediscovery, persistent authorization, connection UI, standalone packaging and real Agent acceptance remain pending. Protocol discovery alone does not prove Core is reachable or the grant valid.

## Validation

Tests cover independent stdio initialization, tool discovery and unknown-tool rejection; an in-memory SDK protocol session drives the real FastAPI application with temporary data for search/read/revocation. URL restrictions and redirect handling are tested without external network or paid providers. These tests do not substitute for packaged desktop or real Agent acceptance.
