"""MCP Server implementation for Oleg Commander."""
import asyncio
import sys
from typing import Optional, Dict, Any
from mcp.server import MCPServer
from .config import Config
from .security import SecurityManager
from .tools.filesystem import FilesystemTool
from .tools.terminal import TerminalTool
from .tools.ssh import SSHTool
from .tools.git import GitTool
from .tools.processes import ProcessTool
from .tools.systemd import SystemdTool
from .tools.docker import DockerTool
from .services.approval_service import ApprovalService

class OlegCommanderServer:
    """Main server class for Oleg Commander MCP server."""
    
    def __init__(self, config: Config):
        self.config = config
        self.security_manager = SecurityManager(config)
        self.approval_service = ApprovalService()
        self.server: Optional[MCPServer] = None
        
        # Initialize tools
        self._tools = {}
        
    async def start(self):
        """Register tools and serve requests until the transport stops."""
        self.server = MCPServer(name=self.config.server.name)
        await self._register_tools()

        if self.config.server.transport == "stdio":
            await self.server.run_stdio_async()
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
        self.server.add_tool(filesystem_tool.list_directory, name="filesystem.list_directory", description="List files and directories")
        self.server.add_tool(filesystem_tool.read_file, name="filesystem.read_file", description="Read text content from a file")
        self.server.add_tool(filesystem_tool.read_multiple_files, name="filesystem.read_multiple_files", description="Read multiple files at once")
        self.server.add_tool(filesystem_tool.write_file, name="filesystem.write_file", description="Write text content to a file")
        self.server.add_tool(filesystem_tool.edit_file, name="filesystem.edit_file", description="Perform find-and-replace in a file")
        self.server.add_tool(filesystem_tool.search_files, name="filesystem.search_files", description="Search files by name pattern")
        self.server.add_tool(filesystem_tool.search_content, name="filesystem.search_content", description="Search for text content in files")
        self.server.add_tool(filesystem_tool.get_file_info, name="filesystem.get_file_info", description="Get information about a file")
        self.server.add_tool(filesystem_tool.create_directory, name="filesystem.create_directory", description="Create a directory")
        self.server.add_tool(filesystem_tool.move_file, name="filesystem.move_file", description="Move a file")
        self.server.add_tool(filesystem_tool.copy_file, name="filesystem.copy_file", description="Copy a file")
        self.server.add_tool(filesystem_tool.delete_file, name="filesystem.delete_file", description="Delete a file")
        
        # Terminal tools
        self.server.add_tool(terminal_tool.execute_command, name="terminal.execute_command", description="Execute a command in the terminal")
        self.server.add_tool(terminal_tool.start_process, name="terminal.start_process", description="Start a process")
        self.server.add_tool(terminal_tool.terminate_process, name="terminal.terminate_process", description="Terminate a process")
        
        # SSH tools
        self.server.add_tool(ssh_tool.ssh_list_hosts, name="ssh.list_hosts", description="List allowed SSH hosts")
        self.server.add_tool(ssh_tool.ssh_connect, name="ssh.connect", description="Check SSH connection to host")
        self.server.add_tool(ssh_tool.ssh_execute, name="ssh.execute", description="Execute a command on SSH host")
        self.server.add_tool(ssh_tool.ssh_read_file, name="ssh.read_file", description="Read file from SSH host")
        self.server.add_tool(ssh_tool.ssh_write_file, name="ssh.write_file", description="Write file to SSH host")
        self.server.add_tool(ssh_tool.ssh_upload, name="ssh.upload", description="Upload file to SSH host")
        self.server.add_tool(ssh_tool.ssh_download, name="ssh.download", description="Download file from SSH host")
        self.server.add_tool(ssh_tool.ssh_disconnect, name="ssh.disconnect", description="Close SSH connection")
        
        # Git tools
        self.server.add_tool(git_tool.git_status, name="git.status", description="Get Git status of a repository")
        self.server.add_tool(git_tool.git_diff, name="git.diff", description="Get Git diff of a repository")
        self.server.add_tool(git_tool.git_log, name="git.log", description="Get Git log of a repository")
        self.server.add_tool(git_tool.git_branches, name="git.branches", description="Get Git branches of a repository")
        self.server.add_tool(git_tool.git_current_branch, name="git.current_branch", description="Get current Git branch")
        self.server.add_tool(git_tool.git_create_branch, name="git.create_branch", description="Create a new Git branch")
        self.server.add_tool(git_tool.git_add, name="git.add", description="Add files to Git staging area")
        self.server.add_tool(git_tool.git_commit, name="git.commit", description="Commit staged files")
        self.server.add_tool(git_tool.git_pull, name="git.pull", description="Pull changes from remote origin")
        self.server.add_tool(git_tool.git_push, name="git.push", description="Push changes to remote origin")
        
        # Process tools
        self.server.add_tool(process_tool.list_processes, name="process.list", description="List running processes")
        self.server.add_tool(process_tool.get_process_info, name="process.info", description="Get information about a process")
        self.server.add_tool(process_tool.kill_process, name="process.kill", description="Kill a running process")
        
        # Systemd tools
        self.server.add_tool(systemd_tool.systemd_status, name="systemd.status", description="Get status of a systemd service")
        self.server.add_tool(systemd_tool.systemd_logs, name="systemd.logs", description="Get logs of a systemd service")
        self.server.add_tool(systemd_tool.systemd_restart, name="systemd.restart", description="Restart a systemd service")
        
        # Docker tools (optional)
        self.server.add_tool(docker_tool.docker_ps, name="docker.ps", description="List running Docker containers")
        self.server.add_tool(docker_tool.docker_logs, name="docker.logs", description="Get logs of a Docker container")
        self.server.add_tool(docker_tool.docker_inspect, name="docker.inspect", description="Inspect a Docker container")
        self.server.add_tool(docker_tool.docker_restart, name="docker.restart", description="Restart a Docker container")
        

        
    async def stop(self):
        """The MCP transport stops when its serving task is cancelled."""
        return None


async def main():
    """Run the MCP server until disconnected or interrupted."""
    await OlegCommanderServer(Config()).start()


if __name__ == "__main__":
    asyncio.run(main())
