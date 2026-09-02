"""Opaque cursor encoding for bounded HTTP collection responses."""

import base64
import binascii
import json
from dataclasses import dataclass

from loredock.application.errors import AppError


@dataclass(frozen=True)
class SourceCursor:
    sort: str
    filter_text: str
    value: str | int
    source_id: str


def encode_source_cursor(cursor: SourceCursor) -> str:
    payload = json.dumps(
        {
            "v": 1,
            "s": cursor.sort,
            "q": cursor.filter_text,
            "k": cursor.value,
            "i": cursor.source_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_source_cursor(value: str, *, sort: str, filter_text: str) -> SourceCursor:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        cursor = SourceCursor(
            sort=str(payload["s"]),
            filter_text=str(payload["q"]),
            value=payload["k"],
            source_id=str(payload["i"]),
        )
        if payload["v"] != 1 or cursor.sort != sort or cursor.filter_text != filter_text:
            raise ValueError
        valid_key = (
            isinstance(cursor.value, str)
            if sort in {"updated-desc", "name-asc"}
            else isinstance(cursor.value, int) and not isinstance(cursor.value, bool)
        )
        if not cursor.source_id or not valid_key:
            raise ValueError
        return cursor
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as error:
        raise AppError("invalid_cursor", "The pagination cursor is invalid.") from error
