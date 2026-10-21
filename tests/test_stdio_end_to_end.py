"""End-to-end MCP over a real CLI stdio subprocess (no network required)."""

import asyncio
import sys

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from oleg_commander.config import Config, LoggingConfig, SecurityConfig
from oleg_commander.server import OlegCommanderServer


class CaptureMCP:
    def __init__(self):
        self.tools = {}

    def add_tool(self, fn, name, description):
        self.tools[name] = fn


def test_unimplemented_tools_are_not_advertised(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    app = OlegCommanderServer(
        Config(
            security=SecurityConfig(read_only=True),
            logging=LoggingConfig(audit_enabled=False),
        )
    )
    app.server = CaptureMCP()
    asyncio.run(app._register_tools())
    forbidden = {
        "process.kill", "git.pull", "git.push",
        "terminal.start_process", "terminal.terminate_process",
    }
    assert not (forbidden & set(app.server.tools))
    for advertised in (
        "process.info", "systemd.status", "docker.ps",
        "git.status", "terminal.execute_command", "ssh.execute",
        "filesystem.read_file", "filesystem.write_file",
    ):
        assert advertised in app.server.tools


async def _stdio_smoke(tmp_path):
    inside = tmp_path / "allowed"
    inside.mkdir()
    target = inside / "hello.txt"
    target.write_text("MCP_SUBPROCESS_READ_OK", encoding="utf-8")
    config_path = tmp_path / "test-config.yaml"
    config_path.write_text(
        "server:\n"
        "  transport: stdio\n"
        "security:\n"
        "  read_only: true\n"
        "  allowed_directories:\n"
        f"    - {inside}\n"
        "logging:\n"
        "  audit_enabled: false\n",
        encoding="utf-8",
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "oleg_commander.cli", "start"],
        env={
            "HOME": str(tmp_path),
            "OLEG_COMMANDER_CONFIG": str(config_path),
        },
    )
    with anyio.fail_after(20):
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                hello = await session.initialize()
                assert hello.server_info.name == "Oleg Commander"

                listing = await session.list_tools()
                names = {tool.name for tool in listing.tools}
                assert "filesystem.read_file" in names
                assert "git.pull" not in names
                assert "process.kill" not in names

                result = await session.call_tool(
                    "filesystem.read_file", {"path": str(target)}
                )
                text = "\n".join(
                    chunk.text for chunk in result.content
                    if hasattr(chunk, "text")
                )
                assert "MCP_SUBPROCESS_READ_OK" in text

                forbidden = await session.call_tool(
                    "filesystem.write_file",
                    {"path": str(target), "content": "OVERWRITE_DENIED"},
                )
                blocked = "\n".join(
                    chunk.text for chunk in forbidden.content
                    if hasattr(chunk, "text")
                )
                assert "READ_ONLY" in blocked
                assert target.read_text() == "MCP_SUBPROCESS_READ_OK"


def test_cli_mcp_stdio_initialization_and_tool_invocation(tmp_path):
    anyio.run(_stdio_smoke, tmp_path)
