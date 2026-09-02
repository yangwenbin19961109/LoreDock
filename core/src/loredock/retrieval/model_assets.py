"""Pinned, checksummed local model asset installation."""

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from loredock.retrieval.embeddings import E5OnnxEmbeddingProvider


@dataclass(frozen=True, slots=True)
class ModelAsset:
    filename: str
    repository_path: str
    sha256: str
    size_bytes: int


E5_MODEL_ID = "intfloat/multilingual-e5-small"
E5_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
E5_ASSETS = (
    ModelAsset(
        "model.onnx",
        "onnx/model_qint8_avx512_vnni.onnx",
        "dd476dd0c2514e9b9be83aeb3853fac0763e0bdf4a71645407587d77c48a2d88",
        118_346_824,
    ),
    ModelAsset(
        "tokenizer.json",
        "onnx/tokenizer.json",
        "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
        17_082_730,
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def validate_e5_package(directory: Path) -> None:
    for asset in E5_ASSETS:
        path = directory / asset.filename
        if not path.is_file() or path.stat().st_size != asset.size_bytes:
            raise ValueError(f"Missing or invalid model asset: {asset.filename}")
        if sha256_file(path) != asset.sha256:
            raise ValueError(f"Checksum mismatch for model asset: {asset.filename}")


def install_e5_package(directory: Path, *, progress: Callable[[str], None] | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for asset in E5_ASSETS:
        destination = directory / asset.filename
        if (
            destination.is_file()
            and destination.stat().st_size == asset.size_bytes
            and sha256_file(destination) == asset.sha256
        ):
            if progress is not None:
                progress(f"Verified {asset.filename}")
            continue
        temporary = destination.with_suffix(destination.suffix + ".part")
        temporary.unlink(missing_ok=True)
        url = (
            f"https://huggingface.co/{E5_MODEL_ID}/resolve/{E5_REVISION}/"
            f"{asset.repository_path}?download=true"
        )
        if progress is not None:
            progress(f"Downloading {asset.filename} ({asset.size_bytes} bytes)")
        request = Request(url, headers={"User-Agent": "LoreDock/0.1 model-installer"})
        try:
            with urlopen(request, timeout=60) as response, temporary.open("wb") as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
            if temporary.stat().st_size != asset.size_bytes:
                raise ValueError(f"Unexpected size for model asset: {asset.filename}")
            if sha256_file(temporary) != asset.sha256:
                raise ValueError(f"Checksum mismatch for model asset: {asset.filename}")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    manifest = {
        "schema_version": 1,
        "model_id": E5_MODEL_ID,
        "revision": E5_REVISION,
        "dimensions": 384,
        "max_length": 512,
        "query_prefix": "query: ",
        "document_prefix": "passage: ",
        "pooling": "attention_mask_mean",
        "normalize": True,
        "assets": [asdict(asset) for asset in E5_ASSETS],
    }
    temporary_manifest = directory / "manifest.json.part"
    temporary_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary_manifest, directory / "manifest.json")
    validate_e5_package(directory)
    return directory


def load_e5_provider(directory: Path) -> E5OnnxEmbeddingProvider:
    validate_e5_package(directory)
    return E5OnnxEmbeddingProvider(
        directory / "model.onnx",
        directory / "tokenizer.json",
        model_checksum=E5_ASSETS[0].sha256,
    )
