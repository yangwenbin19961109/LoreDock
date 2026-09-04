# ADR 0012: Stable connections for copy-to-Agent setup

- Status: Accepted; Core and bridge integration implemented, UI pending
- Date: 2026-09-04
- Decision owners: LoreDock project owner and maintainers
- Supersedes: The process-only persistence limitation in ADR 0010 once integrated

## Context

The owner requested a simpler flow: select libraries and copy a paragraph that asks an Agent to add MCP itself. Copying a dynamic port and temporary token would break on Core restart and expose credentials in conversation history.

## Decision

The intended setup text contains a stable connection ID and a local bridge invocation, not tokens. Persistent connection metadata uses a separate versioned SQLite database; only token hashes, names, scopes, IDs and creation times are stored there. Tokens use an explicit OS credential backend. The existing temporary grant endpoints remain unchanged until the persistent path is fully integrated.

Use `keyring` 25.7.0 (MIT; constrained to 25.x), with only its shipped Windows Credential Locker, macOS Keychain or Linux Secret Service backend selected explicitly. No environment-selected plugin or plaintext fallback is accepted. Backend availability is a runtime requirement; headless Linux and packaged distribution still need validation. See [keyring documentation](https://keyring.readthedocs.io/en/latest/).

Revocation removes the database authorization before deleting the OS secret. Failed secret cleanup is reported separately and never restores access. Failed secret creation does not insert a grant. A crash between vault and database writes may leave an unused secret, never a valid database grant; reconciliation remains follow-up work.

## Boundary

This is same-OS-user local authorization, not isolation against other processes with that user's rights. Knowledge-store backup must not export OS credentials. Metadata schema is v1, separate from `app.sqlite`; full backup/restore integration is pending. Stable endpoint discovery must use validated loopback addresses and must not copy credentials into the discovery file.

## Implementation status and validation

Implemented: persistent storage adapter and explicit OS-vault adapter; owner-only persistent connection API; Core startup/shutdown discovery publication; ID-based bridge startup. Deterministic tests cover restart, no plaintext token in closed SQLite, save failure, revoke cleanup failure, restored HTTP authorization and discovery port changes.

Not yet implemented: UI, generated setup text and Agent acceptance. Tests use an injected fake vault and ASGI HTTP transport; real OS vault behavior, actual socket reconnection and cross-platform packaging are not claimed as verified. A single Core owns each profile. Discovery is a non-secret local file, not a security boundary against other processes under the same OS user.
