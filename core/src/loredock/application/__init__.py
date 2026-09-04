"""Application use cases shared by HTTP and future MCP adapters."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loredock.application.service import LoreDockService


def __getattr__(name: str) -> object:
    # Error contracts are also imported by the lightweight stdio bridge.
    # Preserve the public service export without loading model runtimes for it.
    if name == "LoreDockService":
        from loredock.application.service import LoreDockService

        return LoreDockService
    raise AttributeError(name)


__all__ = ["LoreDockService"]
