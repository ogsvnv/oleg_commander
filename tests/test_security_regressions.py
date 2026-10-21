"""Regression tests for MCP startup and fail-closed permissions."""

import asyncio

import pytest

from oleg_commander.config import Config, SecurityConfig, ServerConfig
from oleg_commander.security import SecurityManager
from oleg_commander.server import OlegCommanderServer
from oleg_commander.tools.git import GitTool
from oleg_commander.tools.ssh import SSHTool
from oleg_commander.tools.terminal import TerminalTool


class FakeMCPServer:
    """Minimal SDK stand-in for deterministic transport and tool checks."""

    created = None

    def __init__(self, name):
        self.name = name
        self.tools = {}
        self.transport = None
        FakeMCPServer.created = self

    def add_tool(self, fn, name, description):
        self.tools[name] = fn

    async def run_stdio_async(self):
        self.transport = "stdio"

    async def run_streamable_http_async(self, *, host, port):
        self.transport = (host, port)


def make_security(*, read_only=True, require_approval=True, **kwargs):
    config = Config(
        security=SecurityConfig(
            read_only=read_only,
            require_approval=require_approval,
            **kwargs,
        )
    )
    return SecurityManager(config)


def test_start_registers_tools_and_uses_stdio(monkeypatch):
    monkeypatch.setattr("oleg_commander.server.MCPServer", FakeMCPServer)
    asyncio.run(OlegCommanderServer(Config()).start())

    mcp = FakeMCPServer.created
    assert mcp.transport == "stdio"
    assert "filesystem.read_file" in mcp.tools
    assert "terminal.execute_command" in mcp.tools
    assert "git.status" in mcp.tools


def test_http_transport_rejects_external_binding(monkeypatch):
    monkeypatch.setattr("oleg_commander.server.MCPServer", FakeMCPServer)
    config = Config(server=ServerConfig(transport="http", host="0.0.0.0"))
    with pytest.raises(ValueError, match="loopback"):
        asyncio.run(OlegCommanderServer(config).start())


def test_http_transport_accepts_loopback(monkeypatch):
    monkeypatch.setattr("oleg_commander.server.MCPServer", FakeMCPServer)
    config = Config(server=ServerConfig(transport="http", host="127.0.0.1"))
    asyncio.run(OlegCommanderServer(config).start())
    assert FakeMCPServer.created.transport == ("127.0.0.1", 8765)


def test_approval_requirement_blocks_modifications():
    assert not make_security(read_only=True, require_approval=False).can_modify()
    assert not make_security(read_only=False, require_approval=True).can_modify()
    assert make_security(read_only=False, require_approval=False).can_modify()


def test_empty_ssh_allowlist_denies_every_host():
    assert not make_security().is_ssh_host_allowed("park")


def test_ssh_stub_returns_failure():
    security = make_security(allowed_ssh_hosts=["park"])
    result = asyncio.run(SSHTool(security).ssh_execute("park", "uname", []))
    assert result.success is False
    assert result.error["code"] == "NOT_IMPLEMENTED"


def test_terminal_denies_arbitrary_command_without_approval():
    tool = TerminalTool(make_security())
    result = asyncio.run(tool.execute_command("sh", ["-c", "echo unsafe"]))
    assert not result.success
    assert result.error["code"] == "FORBIDDEN"


def test_terminal_denies_arguments_to_read_only_commands():
    tool = TerminalTool(make_security())
    result = asyncio.run(tool.execute_command("date", ["-f", "/etc/shadow"]))
    assert not result.success


def test_terminal_denies_outside_working_directory(tmp_path):
    tool = TerminalTool(make_security(allowed_directories=[str(tmp_path)]))
    result = asyncio.run(tool.execute_command("pwd", [], cwd="/etc"))
    assert not result.success
    assert result.error["code"] == "FORBIDDEN"


def test_untracked_processes_cannot_be_started():
    tool = TerminalTool(make_security(read_only=False, require_approval=False))
    result = asyncio.run(tool.start_process("sh", ["-c", "echo unsafe"]))
    assert not result.success
    assert result.error["code"] == "NOT_IMPLEMENTED"


def test_git_pull_is_mutating_even_in_read_only_mode(tmp_path):
    tool = GitTool(make_security(allowed_directories=[str(tmp_path)]))
    result = asyncio.run(tool.git_pull(str(tmp_path)))
    assert not result.success
    assert result.error["code"] == "FORBIDDEN"
