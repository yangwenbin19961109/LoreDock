"""Non-secret loopback endpoint discovery for stable local connection IDs."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def validate_core_url(value: str) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme != "http"
        or parts.hostname not in {"127.0.0.1", "::1"}
        or parts.port is None
        or parts.port == 0
        or parts.username is not None
        or parts.password is not None
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
    ):
        raise ValueError("A numeric loopback Core URL with an explicit port is required.")
    return value.rstrip("/")


class Endpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int = Field(default=1, ge=1, le=1)
    url: str
    instance_id: str


def read_endpoint(profile: Path) -> Endpoint:
    with (profile / "agent-endpoint.json").open("rb") as stream:
        data = stream.read(4097)
    if len(data) > 4096:
        raise ValueError("Invalid discovery record")
    endpoint = Endpoint.model_validate_json(data)
    validate_core_url(endpoint.url)
    return endpoint


def publish_endpoint(profile: Path, url: str) -> Endpoint:
    endpoint = Endpoint(url=validate_core_url(url), instance_id=str(uuid4()))
    profile.mkdir(parents=True, exist_ok=True)
    temporary = profile / f".agent-endpoint-{endpoint.instance_id}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(endpoint.model_dump(), stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(profile / "agent-endpoint.json")
    finally:
        temporary.unlink(missing_ok=True)
    return endpoint


def clear_endpoint(profile: Path, instance_id: str) -> None:
    try:
        if read_endpoint(profile).instance_id == instance_id:
            (profile / "agent-endpoint.json").unlink(missing_ok=True)
    except (OSError, ValueError):
        # Never remove a replacement record that belongs to another Core.
        pass
