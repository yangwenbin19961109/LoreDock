"""Development process entry point."""

import uvicorn

from loredock.app import create_app
from loredock.config import Settings


def main() -> None:
    """Run LoreDock Core using validated local settings."""

    settings = Settings()
    settings.assert_safe_bind_host()
    application = create_app()
    server = uvicorn.Server(
        uvicorn.Config(
            application,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        )
    )
    application.state.desktop_shutdown = lambda: setattr(server, "should_exit", True)
    server.run()


if __name__ == "__main__":
    main()
