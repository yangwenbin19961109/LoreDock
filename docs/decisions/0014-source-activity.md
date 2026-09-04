# ADR 0014: Persistent recent sources and favorites

- Status: Accepted; Core and UI implemented, desktop acceptance pending
- Date: 2026-09-04

## Decision

The owner approved the desktop usability follow-up for recent sources and favorites. Store this user metadata in app.sqlite schema v5, independently of rebuildable indexes. A source_activity row references sources with ON DELETE CASCADE and holds nullable last_opened and favorite_at timestamps. Library deletion also cascades through sources.

An explicit UI visit command updates last_opened; ordinary HTTP/MCP source reads and search do not mutate history. Recent history is deduplicated and capped at 100 sources. Pruning history preserves favorite_at. Favorite PUT is idempotent and does not reorder an already-favorited source. Unfavoriting preserves history.

Collections sort by descending timestamp then source ID, with bounded pages (default/max 50). The initial API accepts offset; Page.next_cursor contains the next numeric offset. This is a live list, not a snapshot: mutations between pages can change positions, so UI should refresh after mutations and deduplicate appended items. MCP exposes no new write tools.

## Migration and verification

Migration v4→v5 creates one table and two indexes, leaving source material and search indexes unchanged. It is safe to reopen/retry; tests cover prior metadata preservation, foreign keys, persistence, pagination, history cap, idempotence, delete cascades and API authentication. Existing older-version migration tests now expect v5.

The old schema-v4 Core refuses the upgraded database; do not downgrade by editing user_version. Before a deployment upgrade, use a WAL-consistent backup. This development turn tested temporary databases only; it did not restart the user's running Core or migrate their active profile.

## Remaining work

Navigation, favorite actions, paginated collections and explicit visit events are implemented. Collections preview the first 8000 characters as safe text; exact main-library page navigation remains a possible follow-up. Test real desktop restart/deletion flows using the new Core; the previously running Core does not reload Python changes automatically.
