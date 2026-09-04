import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from loredock.application.errors import AppError
from loredock.mcp.setup import connection_instructions, connection_setup


def test_setup_contains_id_and_escaped_paths_not_credentials(tmp_path: Path) -> None:
    profile = tmp_path / "用户资料 space"
    text = connection_instructions(profile, "fixture-id")
    config = json.loads(text[text.index("{") :])
    entry = config["mcpServers"]["loredock-fixture-id"]
    assert entry["command"] == sys.executable
    assert entry["args"][-3:] == [str(profile.resolve()), "--connection", "fixture-id"]
    assert "env" not in entry and "LOREDOCK_BRIDGE_TOKEN" not in text
    assert "list_libraries" in text


def test_unbundled_frozen_core_does_not_advertise_python_module_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with pytest.raises(AppError, match="standalone MCP bridge"):
        connection_instructions(tmp_path, "fixture")


def test_packaged_setup_uses_bundled_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "loredock-core.exe"))
    name = "loredock-mcp.exe" if sys.platform == "win32" else "loredock-mcp"
    bridge = tmp_path / "bridge" / "loredock-mcp" / name
    bridge.parent.mkdir(parents=True)
    bridge.touch()
    text = connection_instructions(tmp_path / "profile", "fixture")
    entry = json.loads(text[text.index("{") :])["mcpServers"]["loredock-fixture"]
    assert entry["command"] == str(bridge)
    assert entry["args"] == ["--profile", str(tmp_path / "profile"), "--connection", "fixture"]
    assert "env" not in entry


def test_bridge_import_does_not_load_core_model_runtime() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import loredock.mcp.bridge; import sys; "
            "assert 'onnxruntime' not in sys.modules; "
            "assert 'loredock.application.service' not in sys.modules",
        ],
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


@pytest.mark.parametrize("packaged", [False, True])
def test_manual_configs_round_trip_and_match_instructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, packaged: bool
) -> None:
    monkeypatch.setattr(sys, "frozen", packaged, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "程序 space 🐙" / "core.exe"))
    if packaged:
        name = "loredock-mcp.exe" if sys.platform == "win32" else "loredock-mcp"
        bridge = Path(sys.executable).parent / "bridge" / "loredock-mcp" / name
        bridge.parent.mkdir(parents=True)
        bridge.touch()
    connection_id = 'fixture-"\\\n🐙'
    setup = connection_setup(tmp_path / "资料 space 🐙", connection_id)
    key = f"loredock-{connection_id}"
    original = json.loads(setup.instructions[setup.instructions.index("{") :])["mcpServers"][key]
    codex = tomllib.loads(setup.configurations["codex"])["mcp_servers"][key]
    cursor = json.loads(setup.configurations["cursor"])["mcpServers"][key]
    assert codex == original
    assert cursor == {"type": "stdio", **original}
    assert set(codex) == {"command", "args"}
