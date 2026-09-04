"""Explicit OS credential backends; no configurable plaintext fallback."""

import sys
from importlib import import_module
from typing import Protocol, cast

from loredock.application.errors import AppError


class CredentialVault(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


def system_vault() -> CredentialVault:
    """Select only a shipped secure backend, ignoring third-party backend config."""
    module, class_name = {
        "win32": ("keyring.backends.Windows", "WinVaultKeyring"),
        "darwin": ("keyring.backends.macOS", "Keyring"),
        "linux": ("keyring.backends.SecretService", "Keyring"),
    }.get(sys.platform, ("", ""))
    try:
        if not module:
            raise RuntimeError
        return cast(CredentialVault, getattr(import_module(module), class_name)())
    except Exception as error:
        raise AppError(
            "credential_store_unavailable",
            "The operating system credential store is unavailable.",
            status_code=503,
        ) from error


class LazySystemVault:
    """Do not touch the user's credential store until a connection operation."""

    def get_password(self, service: str, username: str) -> str | None:
        return system_vault().get_password(service, username)

    def set_password(self, service: str, username: str, password: str) -> None:
        system_vault().set_password(service, username, password)

    def delete_password(self, service: str, username: str) -> None:
        system_vault().delete_password(service, username)
