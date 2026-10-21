"""MCP Server implementation for Oleg Commander."""
import asyncio
import inspect
import time
from functools import wraps
from typing import Optional
from mcp.server import MCPServer
from .config import Config
from .services.https_transport import run_https
from .security import SecurityManager
from .tools.filesystem import FilesystemTool
from .tools.terminal import TerminalTool
from .tools.ssh import SSHTool
from .tools.git import GitTool
from .tools.processes import ProcessTool
from .tools.systemd import SystemdTool
from .tools.docker import DockerTool
from .services.approval_service import ApprovalService
from .audit import AuditLogger
from .tool_result import ToolResult

class OlegCommanderServer:
    """Main server class for Oleg Commander MCP server."""
    
    def __init__(self, config: Config):
        self.config = config
        self.security_manager = SecurityManager(config)
        self.approval_service = ApprovalService()
        self.audit = AuditLogger() if config.logging.audit_enabled else None
        self.server: Optional[MCPServer] = None
        
        # Initialize tools
        self._tools = {}
        
    async def start(self):
        """Register tools and serve requests until the transport stops."""
        self.server = MCPServer(name=self.config.server.name)
        await self._register_tools()

        if self.config.server.transport == "stdio":
            await self.server.run_stdio_async()
        elif self.config.server.transport == "https":
            await run_https(self.server, self.config)
        elif self.config.server.transport in ("http", "streamable-http"):
            # Remote exposure is disabled until authentication is implemented.
            if self.config.server.host not in ("127.0.0.1", "::1", "localhost"):
                raise ValueError(
                    "HTTP transport must bind to loopback without authentication"
                )
            await self.server.run_streamable_http_async(
                host=self.config.server.host,
                port=self.config.server.port,
            )
        else:
            raise ValueError(f"Unsupported transport: {self.config.server.transport}")

    MUTATING_TOOLS = frozenset({
        "filesystem.write_file", "filesystem.edit_file",
        "filesystem.create_directory", "filesystem.move_file",
        "filesystem.copy_file", "filesystem.delete_file",
        "git.create_branch", "git.add", "git.commit", "git.pull", "git.push",
        "ssh.write_file", "ssh.upload", "ssh.download",
        "systemd.restart", "docker.restart",
    })
    SAFE_TERMINAL = frozenset({"pwd", "whoami", "uptime", "date", "uname"})
    SAFE_SSH = frozenset({"date", "hostname", "pwd", "uname", "uptime", "whoami"})

    def _mutating(self, name, fn, args, kwargs):
        if name in self.MUTATING_TOOLS:
            return True
        if name not in ("terminal.execute_command", "ssh.execute"):
            return False
        bound = inspect.signature(fn).bind(*args, **kwargs)
        bound.apply_defaults()
        executable = bound.arguments.get("executable")
        arguments = bound.arguments.get("args")
        allow = self.SAFE_TERMINAL if name.startswith("terminal.") else self.SAFE_SSH
        return executable not in allow or bool(arguments)

    def _add_tool(self, fn, *, name, description):
        """Enforce server-side approvals and audit every MCP invocation."""

        @wraps(fn)
        async def guarded(*args, **kwargs):
            started = time.monotonic()
            approval_id = None
            try:
                mutating = self._mutating(name, fn, args, kwargs)
                if mutating and self.config.security.read_only:
                    result = ToolResult(
                        success=False,
                        error={"code": "READ_ONLY", "message": "Read-only mode"},
                    )
                    if self.audit:
                        self.audit.record(tool=name, status="blocked", error_code="READ_ONLY")
                    return result

                # Mutations are forbidden if the operator has disabled audit.
                if mutating and not self.audit:
                    return ToolResult(
                        success=False,
                        error={"code": "AUDIT_REQUIRED", "message": "Audit must be enabled for writes"},
                    )

                if mutating and self.config.security.require_approval:
                    approved, approval_id = self.approval_service.request_or_consume(
                        name, fn, args, kwargs
                    )
                    if not approved:
                        if self.audit:
                            self.audit.record(
                                tool=name, status="approval_required",
                                request_id=approval_id,
                            )
                        return ToolResult(
                            success=False,
                            data={"approval_id": approval_id},
                            error={
                                "code": "APPROVAL_REQUIRED",
                                "message": (
                                    "Approve this exact operation locally using "
                                    f"oleg-commander approve {approval_id}; then retry it"
                                ),
                            },
                        )

                if self.audit:
                    # If the pre-execution audit fails, do not run the tool.
                    self.audit.record(
                        tool=name, status="started", request_id=approval_id,
                    )

                if mutating and approval_id:
                    with self.security_manager.authorized_write():
                        result = await fn(*args, **kwargs)
                else:
                    result = await fn(*args, **kwargs)
                if self.audit:
                    self.audit.record(
                        tool=name,
                        status="success" if result.success else "failed",
                        request_id=approval_id,
                        error_code=(result.error or {}).get("code"),
                        duration_ms=int((time.monotonic() - started) * 1000),
                    )
                return result
            except Exception:
                # Avoid leaking tool arguments, secrets or command output.
                if self.audit:
                    try:
                        self.audit.record(
                            tool=name, status="exception",
                            request_id=approval_id, error_code="INTERNAL_ERROR",
                        )
                    except OSError:
                        pass
                return ToolResult(
                    success=False,
                    error={"code": "INTERNAL_ERROR", "message": "Tool execution failed"},
                )

        self.server.add_tool(guarded, name=name, description=description)

    async def _register_tools(self):
        """Register all available tools."""
        # Create tool instances
        filesystem_tool = FilesystemTool(self.security_manager)
        terminal_tool = TerminalTool(self.security_manager)
        ssh_tool = SSHTool(self.security_manager)
        git_tool = GitTool(self.security_manager)
        process_tool = ProcessTool(self.security_manager)
        systemd_tool = SystemdTool(self.security_manager)
        docker_tool = DockerTool(self.security_manager)
        
        # Register tools with MCP server
        self._add_tool(filesystem_tool.list_directory, name="filesystem.list_directory", description="List files and directories")
        self._add_tool(filesystem_tool.read_file, name="filesystem.read_file", description="Read text content from a file")
        self._add_tool(filesystem_tool.read_multiple_files, name="filesystem.read_multiple_files", description="Read multiple files at once")
        self._add_tool(filesystem_tool.write_file, name="filesystem.write_file", description="Write text content to a file")
        self._add_tool(filesystem_tool.edit_file, name="filesystem.edit_file", description="Perform find-and-replace in a file")
        self._add_tool(filesystem_tool.search_files, name="filesystem.search_files", description="Search files by name pattern")
        self._add_tool(filesystem_tool.search_content, name="filesystem.search_content", description="Search for text content in files")
        self._add_tool(filesystem_tool.get_file_info, name="filesystem.get_file_info", description="Get information about a file")
        self._add_tool(filesystem_tool.create_directory, name="filesystem.create_directory", description="Create a directory")
        self._add_tool(filesystem_tool.move_file, name="filesystem.move_file", description="Move a file")
        self._add_tool(filesystem_tool.copy_file, name="filesystem.copy_file", description="Copy a file")
        self._add_tool(filesystem_tool.delete_file, name="filesystem.delete_file", description="Delete a file")
        
        # Terminal tools
        self._add_tool(terminal_tool.execute_command, name="terminal.execute_command", description="Execute a command in the terminal")
        self._add_tool(terminal_tool.start_process, name="terminal.start_process", description="Start a process")
        self._add_tool(terminal_tool.terminate_process, name="terminal.terminate_process", description="Terminate a process")
        
        # SSH tools
        self._add_tool(ssh_tool.ssh_list_hosts, name="ssh.list_hosts", description="List allowed SSH hosts")
        self._add_tool(ssh_tool.ssh_connect, name="ssh.connect", description="Check SSH connection to host")
        self._add_tool(ssh_tool.ssh_execute, name="ssh.execute", description="Execute a command on SSH host")
        self._add_tool(ssh_tool.ssh_read_file, name="ssh.read_file", description="Read file from SSH host")
        self._add_tool(ssh_tool.ssh_write_file, name="ssh.write_file", description="Write file to SSH host")
        self._add_tool(ssh_tool.ssh_upload, name="ssh.upload", description="Upload file to SSH host")
        self._add_tool(ssh_tool.ssh_download, name="ssh.download", description="Download file from SSH host")
        self._add_tool(ssh_tool.ssh_disconnect, name="ssh.disconnect", description="Close SSH connection")
        
        # Git tools
        self._add_tool(git_tool.git_status, name="git.status", description="Get Git status of a repository")
        self._add_tool(git_tool.git_diff, name="git.diff", description="Get Git diff of a repository")
        self._add_tool(git_tool.git_log, name="git.log", description="Get Git log of a repository")
        self._add_tool(git_tool.git_branches, name="git.branches", description="Get Git branches of a repository")
        self._add_tool(git_tool.git_current_branch, name="git.current_branch", description="Get current Git branch")
        self._add_tool(git_tool.git_create_branch, name="git.create_branch", description="Create a new Git branch")
        self._add_tool(git_tool.git_add, name="git.add", description="Add files to Git staging area")
        self._add_tool(git_tool.git_commit, name="git.commit", description="Commit staged files")
        self._add_tool(git_tool.git_pull, name="git.pull", description="Pull changes from remote origin")
        self._add_tool(git_tool.git_push, name="git.push", description="Push changes to remote origin")
        
        # Process tools
        self._add_tool(process_tool.list_processes, name="process.list", description="List running processes")
        self._add_tool(process_tool.get_process_info, name="process.info", description="Get information about a process")
        self._add_tool(process_tool.kill_process, name="process.kill", description="Kill a running process")
        
        # Systemd tools
        self._add_tool(systemd_tool.systemd_status, name="systemd.status", description="Get status of a systemd service")
        self._add_tool(systemd_tool.systemd_logs, name="systemd.logs", description="Get logs of a systemd service")
        self._add_tool(systemd_tool.systemd_restart, name="systemd.restart", description="Restart a systemd service")
        
        # Docker tools (optional)
        self._add_tool(docker_tool.docker_ps, name="docker.ps", description="List running Docker containers")
        self._add_tool(docker_tool.docker_logs, name="docker.logs", description="Get logs of a Docker container")
        self._add_tool(docker_tool.docker_inspect, name="docker.inspect", description="Inspect a Docker container")
        self._add_tool(docker_tool.docker_restart, name="docker.restart", description="Restart a Docker container")
        

        
    async def stop(self):
        """The MCP transport stops when its serving task is cancelled."""
        return None


async def main():
    """Run the MCP server until disconnected or interrupted."""
    await OlegCommanderServer(Config.load()).start()


if __name__ == "__main__":
    asyncio.run(main())
