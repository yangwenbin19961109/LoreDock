"""Embedding interfaces and the deterministic offline evaluation baseline."""

import hashlib
import math
import re
from collections.abc import Sequence
from importlib import import_module
from itertools import pairwise
from pathlib import Path
from typing import Protocol, cast

import numpy as np
from tokenizers import Tokenizer

Vector = tuple[float, ...]
_TERM = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]", re.IGNORECASE)


class EmbeddingProvider(Protocol):
    identifier: str
    dimensions: int

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]: ...

    def embed_query(self, text: str) -> Vector: ...


class TokenEncoding(Protocol):
    ids: list[int]
    attention_mask: list[int]
    type_ids: list[int]


class BatchTokenizer(Protocol):
    def enable_truncation(self, max_length: int) -> None: ...

    def enable_padding(self, *, pad_id: int, pad_token: str) -> None: ...

    def encode_batch(
        self, inputs: list[str], *, add_special_tokens: bool
    ) -> list[TokenEncoding]: ...


class OnnxInput(Protocol):
    name: str


class OnnxSession(Protocol):
    def get_inputs(self) -> Sequence[OnnxInput]: ...

    def run(self, output_names: None, input_feed: dict[str, np.ndarray]) -> Sequence[object]: ...


class OnnxRuntimeModule(Protocol):
    def InferenceSession(self, path: str, *, providers: list[str]) -> OnnxSession: ...


onnxruntime = cast(OnnxRuntimeModule, import_module("onnxruntime"))


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


class E5OnnxEmbeddingProvider:
    """CPU-only multilingual E5 inference with explicit retrieval semantics."""

    dimensions = 384

    def __init__(
        self,
        model_path: Path,
        tokenizer_path: Path,
        *,
        model_checksum: str,
        batch_size: int = 16,
        max_length: int = 512,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if not 2 <= max_length <= 512:
            raise ValueError("max_length must be between 2 and 512")
        if not model_path.is_file() or not tokenizer_path.is_file():
            raise FileNotFoundError("The E5 ONNX model package is incomplete")
        self.identifier = f"intfloat/multilingual-e5-small@sha256:{model_checksum}"
        self.batch_size = batch_size
        self.tokenizer = cast(BatchTokenizer, Tokenizer.from_file(str(tokenizer_path)))
        self.tokenizer.enable_truncation(max_length=max_length)
        self.tokenizer.enable_padding(pad_id=0, pad_token="<pad>")
        self.session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        self.input_names = {item.name for item in self.session.get_inputs()}

    @staticmethod
    def _normalize(values: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(values, axis=1, keepdims=True)
        return values / np.clip(norms, 1e-12, None)

    def _embed(self, texts: Sequence[str], prefix: str) -> list[Vector]:
        if not texts:
            return []
        vectors: list[Vector] = []
        for offset in range(0, len(texts), self.batch_size):
            batch = [f"{prefix}{text}" for text in texts[offset : offset + self.batch_size]]
            encodings = self.tokenizer.encode_batch(batch, add_special_tokens=True)
            input_ids = np.asarray([encoding.ids for encoding in encodings], dtype=np.int64)
            attention_mask = np.asarray(
                [encoding.attention_mask for encoding in encodings], dtype=np.int64
            )
            feed: dict[str, np.ndarray] = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }
            if "token_type_ids" in self.input_names:
                feed["token_type_ids"] = np.asarray(
                    [encoding.type_ids for encoding in encodings], dtype=np.int64
                )
            unsupported = self.input_names.difference(feed)
            if unsupported:
                raise RuntimeError(f"Unsupported E5 ONNX inputs: {sorted(unsupported)}")
            last_hidden = np.asarray(self.session.run(None, feed)[0], dtype=np.float32)
            mask = attention_mask[..., None].astype(np.float32)
            pooled = (last_hidden * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-12, None)
            normalized = self._normalize(pooled)
            vectors.extend(tuple(float(value) for value in row) for row in normalized)
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        return self._embed(texts, "passage: ")

    def embed_query(self, text: str) -> Vector:
        return self._embed([text], "query: ")[0]
