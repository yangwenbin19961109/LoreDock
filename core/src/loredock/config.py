"""Runtime configuration loaded from environment variables."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated settings for a LoreDock Core process."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LOREDOCK_",
        extra="ignore",
    )

    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=49321, ge=1024, le=65535)
    log_level: str = "info"
    data_dir: Path | None = None

    def resolved_data_dir(self) -> Path:
        return (self.data_dir or Path.cwd() / "data").resolve()

    def assert_safe_bind_host(self) -> None:
        """Reject non-loopback binding unless a later server profile opts in explicitly."""

        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("LoreDock Core must bind to a loopback address in local mode")
