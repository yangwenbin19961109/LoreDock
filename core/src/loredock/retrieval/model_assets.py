"""Pinned, checksummed local model asset installation."""

import hashlib
import json
import os
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from loredock.retrieval.embeddings import E5OnnxEmbeddingProvider

DownloadProgress = Callable[[int, int, str], None]


class ModelDownloadCancelled(Exception):
    """Raised at a safe block boundary when a model download is canceled."""


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
MODEL_INSTALL_RESERVE_BYTES = 256 * 1024 * 1024


def required_e5_install_bytes() -> int:
    """Return a conservative free-space requirement for verified atomic downloads."""

    return sum(asset.size_bytes for asset in E5_ASSETS) + MODEL_INSTALL_RESERVE_BYTES


def ensure_e5_install_space(directory: Path) -> int:
    directory.parent.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(directory.parent).free
    required_bytes = required_e5_install_bytes()
    if free_bytes < required_bytes:
        raise OSError(
            f"Insufficient disk space for model installation: {free_bytes} available, "
            f"{required_bytes} required"
        )
    return free_bytes


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


def install_e5_package(
    directory: Path,
    *,
    progress: DownloadProgress | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Path:
    ensure_e5_install_space(directory)
    directory.mkdir(parents=True, exist_ok=True)
    completed_bytes = 0
    total_bytes = sum(asset.size_bytes for asset in E5_ASSETS)
    for asset in E5_ASSETS:
        destination = directory / asset.filename
        if (
            destination.is_file()
            and destination.stat().st_size == asset.size_bytes
            and sha256_file(destination) == asset.sha256
        ):
            completed_bytes += asset.size_bytes
            if progress is not None:
                progress(completed_bytes, total_bytes, asset.filename)
            continue
        temporary = destination.with_suffix(destination.suffix + ".part")
        offset = temporary.stat().st_size if temporary.exists() else 0
        if offset > asset.size_bytes:
            temporary.unlink()
            offset = 0
        url = (
            f"https://huggingface.co/{E5_MODEL_ID}/resolve/{E5_REVISION}/"
            f"{asset.repository_path}?download=true"
        )
        headers = {"User-Agent": "LoreDock/0.1 model-installer"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=15) as response:
                resumed = offset > 0 and getattr(response, "status", None) == 206
                if not resumed:
                    offset = 0
                with temporary.open("ab" if resumed else "wb") as output:
                    downloaded = offset
                    if progress is not None:
                        progress(completed_bytes + downloaded, total_bytes, asset.filename)
                    while block := response.read(1024 * 1024):
                        if should_cancel is not None and should_cancel():
                            raise ModelDownloadCancelled()
                        output.write(block)
                        downloaded += len(block)
                        if progress is not None:
                            progress(completed_bytes + downloaded, total_bytes, asset.filename)
            if temporary.stat().st_size != asset.size_bytes:
                raise ValueError(f"Unexpected size for model asset: {asset.filename}")
            if sha256_file(temporary) != asset.sha256:
                temporary.unlink(missing_ok=True)
                raise ValueError(f"Checksum mismatch for model asset: {asset.filename}")
            os.replace(temporary, destination)
            completed_bytes += asset.size_bytes
        except ModelDownloadCancelled:
            raise
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
