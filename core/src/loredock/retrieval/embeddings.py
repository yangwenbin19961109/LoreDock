"""Embedding interfaces and the deterministic offline evaluation baseline."""

import hashlib
import math
import re
from collections.abc import Sequence
from itertools import pairwise
from typing import Protocol

Vector = tuple[float, ...]
_TERM = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]", re.IGNORECASE)


class EmbeddingProvider(Protocol):
    identifier: str
    dimensions: int

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]: ...

    def embed_query(self, text: str) -> Vector: ...


class HashingEmbeddingProvider:
    """Dependency-free semantic-pipeline fixture; not a production embedding model."""

    identifier = "loredock/hash-v1"

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8")
        self.dimensions = dimensions

    def _embed(self, text: str) -> Vector:
        values = [0.0] * self.dimensions
        terms = _TERM.findall(text.lower())
        features = terms + ["".join(pair) for pair in pairwise(terms)]
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            values[bucket] += sign
        norm = math.sqrt(sum(value * value for value in values))
        if norm:
            values = [value / norm for value in values]
        return tuple(values)

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> Vector:
        return self._embed(text)
