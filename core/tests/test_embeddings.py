import hashlib
from pathlib import Path

import numpy as np
import pytest

from loredock.retrieval import embeddings, model_assets
from loredock.retrieval.embeddings import E5OnnxEmbeddingProvider
from loredock.retrieval.model_assets import ModelAsset


class FakeEncoding:
    def __init__(self, token: int) -> None:
        self.ids = [token, token + 1]
        self.attention_mask = [1, 1]
        self.type_ids = [0, 0]


class FakeTokenizer:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    def enable_truncation(self, max_length: int) -> None:
        assert max_length == 512

    def enable_padding(self, *, pad_id: int, pad_token: str) -> None:
        assert (pad_id, pad_token) == (0, "<pad>")

    def encode_batch(self, inputs: list[str], *, add_special_tokens: bool) -> list[FakeEncoding]:
        assert add_special_tokens is True
        self.inputs.extend(inputs)
        return [FakeEncoding(2 if text.startswith("query: ") else 3) for text in inputs]


class FakeInput:
    name = "input_ids"


class FakeSession:
    def get_inputs(self) -> list[FakeInput]:
        return [FakeInput()]

    def run(self, _output_names: None, input_feed: dict[str, np.ndarray]) -> list[np.ndarray]:
        input_ids = input_feed["input_ids"]
        output = np.zeros((*input_ids.shape, 384), dtype=np.float32)
        output[:, :, 0] = input_ids
        output[:, :, 1] = 1.0
        return [output]


class FakeOnnxRuntime:
    def InferenceSession(self, _path: str, *, providers: list[str]) -> FakeSession:
        assert providers == ["CPUExecutionProvider"]
        return FakeSession()


def test_e5_provider_applies_prefix_pooling_and_normalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = tmp_path / "model.onnx"
    tokenizer_file = tmp_path / "tokenizer.json"
    model.write_bytes(b"model")
    tokenizer_file.write_text("{}", encoding="utf-8")
    tokenizer = FakeTokenizer()

    def load_tokenizer(_path: str) -> FakeTokenizer:
        return tokenizer

    monkeypatch.setattr(embeddings.Tokenizer, "from_file", load_tokenizer)
    monkeypatch.setattr(embeddings, "onnxruntime", FakeOnnxRuntime())
    provider = E5OnnxEmbeddingProvider(model, tokenizer_file, model_checksum="checksum")

    query = provider.embed_query("question")
    document = provider.embed_documents(["answer"])[0]

    assert tokenizer.inputs == ["query: question", "passage: answer"]
    assert len(query) == len(document) == 384
    assert abs(float(np.linalg.norm(query)) - 1.0) < 1e-6
    assert abs(float(np.linalg.norm(document)) - 1.0) < 1e-6


def test_model_package_validation_rejects_corruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"verified model"
    asset = ModelAsset(
        "model.onnx", "remote/model.onnx", hashlib.sha256(payload).hexdigest(), len(payload)
    )
    monkeypatch.setattr(model_assets, "E5_ASSETS", (asset,))
    path = tmp_path / asset.filename
    path.write_bytes(payload)

    model_assets.validate_e5_package(tmp_path)
    path.write_bytes(b"corrupt model")

    with pytest.raises(ValueError, match="invalid model asset"):
        model_assets.validate_e5_package(tmp_path)
