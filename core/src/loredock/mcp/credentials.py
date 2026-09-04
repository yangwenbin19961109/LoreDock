"""Process-local, revocable read grants; only token digests are retained."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from loredock.application.errors import AppError


@dataclass(frozen=True)
class ReadGrant:
    id: str
    library_ids: frozenset[str]
    name: str
    created_at: str


class ReadGrantStore:
    def __init__(self) -> None:
        self._entries: dict[bytes, ReadGrant] = {}
        self._lock = RLock()

    def issue(self, library_ids: frozenset[str], name: str = "Agent") -> tuple[ReadGrant, str]:
        token = secrets.token_urlsafe(32)
        grant = ReadGrant(str(uuid4()), library_ids, name, datetime.now(UTC).isoformat())
        with self._lock:
            if len(self._entries) >= 100:
                raise AppError(
                    "grant_limit_reached",
                    "Revoke an existing connection before creating another.",
                    status_code=409,
                )
            self._entries[hashlib.sha256(token.encode()).digest()] = grant
        return grant, token

    def list_grants(self) -> list[ReadGrant]:
        """Bounded metadata snapshot; never returns tokens or digests."""
        with self._lock:
            return sorted(self._entries.values(), key=lambda grant: grant.created_at, reverse=True)

    def resolve(self, token: str) -> ReadGrant | None:
        digest = hashlib.sha256(token.encode()).digest()
        with self._lock:
            return self._entries.get(digest)

    def revoke(self, grant_id: str) -> None:
        with self._lock:
            self._entries = {
                key: value for key, value in self._entries.items() if value.id != grant_id
            }
