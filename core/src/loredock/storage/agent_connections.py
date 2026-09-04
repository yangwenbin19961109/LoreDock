"""Persistent connection metadata with OS-vault secrets and stable identifiers."""

import hashlib
import json
import os
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

from loredock.application.errors import AppError
from loredock.mcp.credentials import ReadGrant
from loredock.storage.credential_vault import CredentialVault


def connection_service_name(path: Path) -> str:
    identity = os.path.normcase(str(path.resolve()))
    return "LoreDock.Agent." + hashlib.sha256(identity.encode()).hexdigest()


class AgentConnectionStore:
    """One Core owns this store; bridges receive IDs, never the owner token.

    Tokens live only in the supplied OS vault. SQLite contains metadata and
    token hashes. Revocation commits to SQLite before best-effort vault cleanup.
    """

    def __init__(self, path: Path, vault: CredentialVault) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._vault = vault
        self.service_name = connection_service_name(path)
        self._lock = RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self._db.close()
            raise AppError("connection_schema_unsupported", "Connection metadata is incompatible.")
        with self._db:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS connections (id TEXT PRIMARY KEY, "
                "name TEXT NOT NULL, created_at TEXT NOT NULL, library_ids TEXT NOT NULL, "
                "token_hash BLOB NOT NULL UNIQUE)"
            )
            self._db.execute("PRAGMA user_version=1")

    @staticmethod
    def _grant(row: sqlite3.Row) -> ReadGrant:
        return ReadGrant(
            row["id"], frozenset(json.loads(row["library_ids"])), row["name"], row["created_at"]
        )

    def issue(self, library_ids: frozenset[str], name: str = "Agent") -> ReadGrant:
        name = name.strip()
        if not name or len(name) > 120 or not 1 <= len(library_ids) <= 100:
            raise AppError("invalid_connection", "Connection name or library scope is invalid.")
        if any(not item or len(item) > 128 for item in library_ids):
            raise AppError("invalid_connection", "Library identifiers are invalid.")
        grant = ReadGrant(str(uuid4()), library_ids, name, datetime.now(UTC).isoformat())
        token = secrets.token_urlsafe(32)
        with self._lock:
            if self._db.execute("SELECT COUNT(*) FROM connections").fetchone()[0] >= 100:
                raise AppError("grant_limit_reached", "Revoke an existing connection first.")
            try:
                self._vault.set_password(self.service_name, grant.id, token)
                # Some unavailable backends silently discard writes; fail closed.
                if self._vault.get_password(self.service_name, grant.id) != token:
                    raise RuntimeError
            except Exception as error:
                self._cleanup_secret(grant.id)
                raise AppError(
                    "credential_store_unavailable",
                    "Unable to securely save the connection.",
                    status_code=503,
                ) from error
            try:
                with self._db:
                    self._db.execute(
                        "INSERT INTO connections VALUES (?, ?, ?, ?, ?)",
                        (
                            grant.id,
                            grant.name,
                            grant.created_at,
                            json.dumps(sorted(library_ids)),
                            hashlib.sha256(token.encode()).digest(),
                        ),
                    )
            except Exception:
                self._cleanup_secret(grant.id)
                raise
        return grant

    def _cleanup_secret(self, grant_id: str) -> bool:
        try:
            self._vault.delete_password(self.service_name, grant_id)
            return True
        except Exception:
            return False

    def list_grants(self) -> list[ReadGrant]:
        with self._lock:
            return [
                self._grant(row)
                for row in self._db.execute(
                    "SELECT * FROM connections ORDER BY created_at DESC, id"
                ).fetchall()
            ]

    def resolve(self, token: str) -> ReadGrant | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM connections WHERE token_hash=?",
                (hashlib.sha256(token.encode()).digest(),),
            ).fetchone()
            return self._grant(row) if row else None

    def connection_token(self, grant_id: str) -> str:
        """Internal bridge use only; never expose this in the copy-to-Agent text."""
        with self._lock:
            row = self._db.execute("SELECT * FROM connections WHERE id=?", (grant_id,)).fetchone()
            if row is None:
                raise AppError("connection_not_found", "Connection was revoked or does not exist.")
            try:
                token = self._vault.get_password(self.service_name, grant_id)
            except Exception as error:
                raise AppError(
                    "credential_store_unavailable",
                    "Unlock the system credential store.",
                    status_code=503,
                ) from error
            resolved = self.resolve(token) if token is not None else None
            if token is None or resolved is None or resolved.id != grant_id:
                raise AppError("credential_missing", "Recreate this connection in LoreDock.")
            return token

    def revoke(self, grant_id: str) -> bool:
        """Return whether vault cleanup succeeded; access is revoked either way."""
        with self._lock:
            with self._db:
                self._db.execute("DELETE FROM connections WHERE id=?", (grant_id,))
            return self._cleanup_secret(grant_id)

    def close(self) -> None:
        self._db.close()
