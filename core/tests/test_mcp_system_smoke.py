"""Opt-in local socket/stdio/OS-vault acceptance; never uses personal profiles."""

import asyncio
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tomllib
from contextlib import aclosing
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from loredock.storage.agent_connections import AgentConnectionStore
from loredock.storage.credential_vault import system_vault


@pytest.mark.skipif(
    os.environ.get("LOREDOCK_TEST_SYSTEM_VAULT") != "1",
    reason="Explicit opt-in required: creates and removes isolated OS-vault credentials",
)
def test_real_vault_stdio_and_core_restart(tmp_path: Path) -> None:
    async def run() -> None:
        owner_token = secrets.token_urlsafe(32)
        processes: list[subprocess.Popen[bytes]] = []
        used_ports: set[int] = set()

        async def start_core() -> httpx.AsyncClient:
            while True:
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", 0))
                    port = listener.getsockname()[1]
                if port not in used_ports:
                    used_ports.add(port)
                    break
            env = {
                key: value for key, value in os.environ.items() if not key.startswith("LOREDOCK_")
            }
            env.update(
                LOREDOCK_DATA_DIR=str(tmp_path),
                LOREDOCK_DESKTOP_TOKEN=owner_token,
                LOREDOCK_PORT=str(port),
                LOREDOCK_HOST="127.0.0.1",
            )
            process = subprocess.Popen(
                [os.environ["LOREDOCK_TEST_CORE_EXE"]]
                if os.environ.get("LOREDOCK_TEST_CORE_EXE")
                else [sys.executable, "-m", "loredock"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            processes.append(process)
            client = httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}",
                trust_env=False,
                timeout=2,
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            for _ in range(100):
                if process.poll() is not None:
                    break
                try:
                    if (await client.get("/api/v1/libraries")).status_code == 200:
                        return client
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.1)
            await client.aclose()
            raise AssertionError("Isolated Core did not become ready")

        try:
            async with aclosing(await start_core()) as owner:
                library = await owner.post("/api/v1/libraries", json={"name": "Smoke fixture"})
                library.raise_for_status()
                library_id = library.json()["id"]
                fixture_text = "LoreDock acceptance fixture: moonstone retention is 17 days."
                uploaded = await owner.post(
                    f"/api/v1/libraries/{library_id}/sources",
                    files={"file": ("acceptance.txt", fixture_text.encode(), "text/plain")},
                )
                uploaded.raise_for_status()
                source_id = uploaded.json()["source"]["id"]
                denied = await owner.post("/api/v1/libraries", json={"name": "Not granted"})
                denied.raise_for_status()
                created = await owner.post(
                    "/api/v1/agent-connections",
                    json={"name": "Isolated smoke", "library_ids": [library_id]},
                )
                assert created.status_code == 200, "System vault connection creation failed"
                connection_id = created.json()["id"]
                setup = await owner.get(f"/api/v1/agent-connections/{connection_id}/setup")
                setup.raise_for_status()
                instructions = setup.json()["instructions"]
                entry = json.loads(instructions[instructions.index("{") :])["mcpServers"][
                    f"loredock-{connection_id}"
                ]
                parameters = StdioServerParameters(
                    command=entry["command"],
                    args=entry["args"],
                )
                if os.environ.get("LOREDOCK_TEST_CODEX") == "1":
                    executable = shutil.which("codex")
                    assert executable, "Codex CLI is required for explicit live acceptance"
                    workspace = tmp_path / "empty-agent-workspace"
                    workspace.mkdir()
                    config_args = [
                        "-c",
                        "mcp_servers.loredock_acceptance.command=" + json.dumps(entry["command"]),
                        "-c",
                        "mcp_servers.loredock_acceptance.args=" + json.dumps(entry["args"]),
                        "-c",
                        "mcp_servers.loredock_acceptance.required=true",
                    ]
                    if os.environ.get("LOREDOCK_TEST_CODEX_SETUP") == "1":
                        config_dir = workspace / ".codex"
                        config_dir.mkdir()
                        config_path = config_dir / "config.toml"
                        shutil.copyfile(
                            Path(__file__).parent / "fixtures" / "agent-config.toml", config_path
                        )
                        trust = "projects." + json.dumps(str(workspace)) + '.trust_level="trusted"'
                        setup_command = [
                            executable,
                            "exec",
                            "--ignore-user-config",
                            "--ephemeral",
                            "--skip-git-repo-check",
                            "--sandbox",
                            "workspace-write",
                            "--json",
                            "-C",
                            str(workspace),
                            "--add-dir",
                            str(config_dir),
                            "-c",
                            trust,
                            "Only edit this temporary project's .codex/config.toml; "
                            "never edit global config or other directories. Preserve the existing "
                            "keep_fixture disabled server exactly. You are authorized to merge "
                            "the following setup now. Do not invoke nested agents. A fresh session "
                            "will test the saved MCP config; do not claim connection success yet.\n"
                            + instructions,
                        ]
                        setup_result = await asyncio.to_thread(
                            subprocess.run,
                            setup_command,
                            capture_output=True,
                            timeout=150,
                            encoding="utf-8",
                            errors="replace",
                            check=False,
                        )
                        assert setup_result.returncode == 0, "Codex setup invocation failed"
                        merged = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
                        expected_name = f"loredock-{connection_id}"
                        if expected_name not in merged.get("mcp_servers", {}):
                            # Report only categories; never dump model responses or tool logs.
                            diagnostic = (setup_result.stdout + setup_result.stderr).lower()
                            print(
                                "Setup incomplete; mentions permission:",
                                any(
                                    word in diagnostic for word in ("permission", "denied", "权限")
                                ),
                                "mentions sandbox:",
                                "sandbox" in diagnostic,
                            )
                            raise AssertionError(
                                "Codex exited but did not save the requested MCP entry; "
                                "automatic setup is not accepted"
                            )
                        assert set(merged) == {"mcp_servers"}
                        assert set(merged["mcp_servers"]) == {
                            "keep_fixture",
                            f"loredock-{connection_id}",
                        }
                        assert merged["mcp_servers"]["keep_fixture"] == {
                            "command": "fixture-do-not-run",
                            "enabled": False,
                            "args": ["preserve-me"],
                        }
                        saved = merged["mcp_servers"][f"loredock-{connection_id}"]
                        assert saved["command"] == entry["command"]
                        assert saved["args"] == entry["args"]
                        assert "env" not in saved
                        assert set(saved) <= {
                            "command",
                            "args",
                            "enabled",
                            "required",
                            "startup_timeout_sec",
                            "tool_timeout_sec",
                        }
                        print("Codex project config merge: verified; existing service preserved")
                        # Do not inject MCP command/args: the second process must load the file.
                        config_args = ["-c", trust]
                    command = [
                        executable,
                        "exec",
                        "--ignore-user-config",
                        "--ephemeral",
                        "--skip-git-repo-check",
                        "--sandbox",
                        "read-only",
                        "--json",
                        "-C",
                        str(workspace),
                        *config_args,
                        "Use only LoreDock MCP tools, not shell or filesystem. "
                        "Call list_libraries, "
                        "search_knowledge for moonstone with lexical_only=true, then read_source "
                        "using a returned read_reference. Report the retention period and cite the "
                        "source name and character range. "
                        "Do not change any configuration or files.",
                    ]
                    # Keep raw provider responses in memory only, never in logs or fixtures.
                    completed = await asyncio.to_thread(
                        subprocess.run,
                        command,
                        capture_output=True,
                        timeout=150,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                    )
                    events = [
                        json.loads(line)
                        for line in completed.stdout.splitlines()
                        if line.startswith("{")
                    ]
                    items = [
                        event.get("item", {})
                        for event in events
                        if event.get("type") == "item.completed"
                    ]
                    calls = [item for item in items if item.get("type") == "mcp_tool_call"]
                    passed = {
                        item.get("tool")
                        for item in calls
                        if item.get("status") == "completed" and not item.get("error")
                    }
                    print(
                        "Codex exit:", completed.returncode, "completed MCP tools:", sorted(passed)
                    )
                    assert completed.returncode == 0, (
                        "Codex live invocation failed; no raw logs saved"
                    )
                    assert {"list_libraries", "search_knowledge", "read_source"} <= passed
                    answers = " ".join(
                        str(item.get("text", ""))
                        for item in items
                        if item.get("type") == "agent_message"
                    )
                    assert "17" in answers and "acceptance.txt" in answers
                async with (
                    stdio_client(parameters) as (read, write),
                    ClientSession(read, write) as session,
                ):
                    await session.initialize()
                    assert len((await session.list_tools()).tools) == 6
                    listed = await session.call_tool("list_libraries", {})
                    assert not listed.isError and listed.structuredContent is not None
                    assert [item["id"] for item in listed.structuredContent["items"]] == [
                        library_id
                    ]
                    forbidden = await session.call_tool(
                        "list_sources", {"library_id": denied.json()["id"]}
                    )
                    assert forbidden.isError
                    searched = await session.call_tool(
                        "search_knowledge",
                        {"library_id": library_id, "query": "moonstone", "lexical_only": True},
                    )
                    assert not searched.isError and searched.structuredContent is not None
                    hits = searched.structuredContent["items"]
                    assert hits and hits[0]["source_id"] == source_id
                    excerpt = await session.call_tool("read_source", hits[0]["read_reference"])
                    assert not excerpt.isError and excerpt.structuredContent is not None
                    assert "17 days" in excerpt.structuredContent["text"]
                    crossed = await session.call_tool(
                        "read_source", {"library_id": denied.json()["id"], "source_id": source_id}
                    )
                    assert crossed.isError
                    processes[-1].terminate()
                    await asyncio.to_thread(processes[-1].wait, 10)
                    assert (await session.call_tool("list_libraries", {})).isError
                    async with aclosing(await start_core()) as restarted:
                        restored = await session.call_tool("list_libraries", {})
                        assert not restored.isError
                        assert restored.structuredContent == listed.structuredContent
                        reread = await session.call_tool("read_source", hits[0]["read_reference"])
                        assert not reread.isError
                        assert reread.structuredContent == excerpt.structuredContent
                        revoked = await restarted.delete(
                            f"/api/v1/agent-connections/{connection_id}"
                        )
                        assert revoked.json() == {"revoked": True, "credential_removed": True}
                        assert (await session.call_tool("list_libraries", {})).isError
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    await asyncio.to_thread(process.wait, 10)
            # Only this pytest temporary profile's grants can be removed.
            store = AgentConnectionStore(tmp_path / "agent-connections.sqlite", system_vault())
            try:
                for grant in store.list_grants():
                    assert store.revoke(grant.id), "Test credential cleanup failed"
            finally:
                store.close()

    asyncio.run(asyncio.wait_for(run(), timeout=390))
