"""Development process entry point."""

import uvicorn

from loredock.config import Settings


def main() -> None:
    """Run LoreDock Core using validated local settings."""

    settings = Settings()
    settings.assert_safe_bind_host()
    uvicorn.run(
        "loredock.app:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
