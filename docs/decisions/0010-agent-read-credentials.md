# ADR 0010: Separate Agent read credentials from desktop authority

- Status: Accepted
- Date: 2026-09-04
- Decision owners: LoreDock maintainers

## Context

The desktop Bearer token authorizes Core management, including source deletion and shutdown. A local Agent bridge must not receive this authority.

## Decision

Add dedicated read credentials with explicit library scopes. Only the authenticated desktop owner can issue or revoke credentials through `/api/v1/agent-grants`. Plain tokens are returned once with `Cache-Control: no-store`; the process keeps only SHA-256 digests and immutable grants.

Only `/api/v1/agent-tools/call` uses read credential authentication. It always requires a valid read grant, including when desktop authentication is not configured. Other endpoints retain desktop authentication. Credential administration is disabled without desktop authentication.

Tool requests are limited to 32 KiB and execute synchronous Core use cases in a worker thread. This internal HTTP endpoint is not an MCP transport.

## Alternatives considered

- Sharing the desktop token: rejected because it grants writes and process control.
- Trusting library IDs submitted by the Agent: rejected because input is not authorization.
- Adding persistent secret storage in this increment: deferred until OS credential-store integration is designed and tested.

## Consequences

Credentials are process-local, have no persistent secret file, and expire on Core restart. Revocation blocks subsequent authentication, not already-authorized in-flight calls. The desktop connection wizard, OS credential store, expiry policy, grant inventory and stdio protocol remain follow-up work. No database migration is required. Local HTTP remains loopback-only; remote deployment is outside this increment.

## Validation

HTTP integration tests cover unauthenticated access, owner/read-token separation, library scope, write and shutdown rejection, revocation, invalid payloads and body-size limits. A new credential store does not recognize old tokens.
