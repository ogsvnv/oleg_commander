"""Exercise the real MCP initialize/list_tools/call_tool wire protocol."""

import anyio
from mcp.client.session import ClientSession
from mcp.server import MCPServer

from oleg_commander.config import Config, LoggingConfig, SecurityConfig
from oleg_commander.server import OlegCommanderServer


async def _roundtrip(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "inside.txt").write_text("HELLO_FROM_MCP")
    outside = tmp_path / "outside.txt"
    outside.write_text("SECRET_OUTSIDE_MCP")

    app = OlegCommanderServer(
        Config(
            security=SecurityConfig(
                read_only=True,
                allowed_directories=[str(allowed)],
            ),
            logging=LoggingConfig(audit_enabled=False),
        )
    )
    app.server = MCPServer("Oleg Commander Integration")
    await app._register_tools()

    # Full-duplex pair of memory transports, no sockets and no real SSH hosts.
    client_to_server_send, client_to_server_recv = anyio.create_memory_object_stream(100)
    server_to_client_send, server_to_client_recv = anyio.create_memory_object_stream(100)

    async def serve():
        await app.server._lowlevel_server.run(
            client_to_server_recv,
            server_to_client_send,
            app.server._lowlevel_server.create_initialization_options(),
            raise_exceptions=True,
        )

    with anyio.fail_after(15):
        async with (
            client_to_server_send,
            client_to_server_recv,
            server_to_client_send,
            server_to_client_recv,
            anyio.create_task_group() as tasks,
        ):
            tasks.start_soon(serve)
            async with ClientSession(
                server_to_client_recv,
                client_to_server_send,
            ) as session:
                initialization = await session.initialize()
                assert initialization.server_info.name == "Oleg Commander Integration"

                listed = await session.list_tools()
                names = {item.name for item in listed.tools}
                assert "filesystem.read_file" in names
                assert "filesystem.write_file" in names

                read = await session.call_tool(
                    "filesystem.read_file", {"path": str(allowed / "inside.txt")}
                )
                text = "\n".join(block.text for block in read.content if hasattr(block, "text"))
                assert "HELLO_FROM_MCP" in text

                forbidden = await session.call_tool(
                    "filesystem.read_file", {"path": str(outside)}
                )
                denied = "\n".join(
                    block.text for block in forbidden.content
                    if hasattr(block, "text")
                )
                assert "FORBIDDEN" in denied
                assert "SECRET_OUTSIDE_MCP" not in denied

                mutation = await session.call_tool(
                    "filesystem.write_file",
                    {"path": str(allowed / "inside.txt"), "content": "unsafe"},
                )
                blocked = "\n".join(
                    block.text for block in mutation.content
                    if hasattr(block, "text")
                )
                assert "READ_ONLY" in blocked
                assert (allowed / "inside.txt").read_text() == "HELLO_FROM_MCP"
            tasks.cancel_scope.cancel()


def test_real_mcp_transport_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    anyio.run(_roundtrip, tmp_path)
