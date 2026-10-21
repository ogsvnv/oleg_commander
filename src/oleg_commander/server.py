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
        """Start the MCP server."""
        print("Starting Oleg Commander server...")
        
        # Create the MCP server
        if self.config.server.transport == "stdio":
            self.server = MCPServer(
                name=self.config.server.name,
                transport="stdio"
            )
        else:
            self.server = MCPServer(
                name=self.config.server.name,
                transport="http",
                host=self.config.server.host,
                port=self.config.server.port
            )
        
        # Register tools with the server
        await self._register_tools()
        
        # Start the server
        await self.server.start()
        print(f"Oleg Commander server started on {self.config.server.transport}")
        
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
        self.server.register_tool("filesystem.list_directory", 
                                filesystem_tool.list_directory, 
                                description="List files and directories")
        self.server.register_tool("filesystem.read_file", 
                                filesystem_tool.read_file, 
                                description="Read text content from a file")
        self.server.register_tool("filesystem.read_multiple_files", 
                                filesystem_tool.read_multiple_files, 
                                description="Read multiple files at once")
        self.server.register_tool("filesystem.write_file", 
                                filesystem_tool.write_file, 
                                description="Write text content to a file")
        self.server.register_tool("filesystem.edit_file", 
                                filesystem_tool.edit_file, 
                                description="Perform find-and-replace in a file")
        self.server.register_tool("filesystem.search_files", 
                                filesystem_tool.search_files, 
                                description="Search files by name pattern")
        self.server.register_tool("filesystem.search_content", 
                                filesystem_tool.search_content, 
                                description="Search for text content in files")
        self.server.register_tool("filesystem.get_file_info", 
                                filesystem_tool.get_file_info, 
                                description="Get information about a file")
        self.server.register_tool("filesystem.create_directory", 
                                filesystem_tool.create_directory, 
                                description="Create a directory")
        self.server.register_tool("filesystem.move_file", 
                                filesystem_tool.move_file, 
                                description="Move a file")
        self.server.register_tool("filesystem.copy_file", 
                                filesystem_tool.copy_file, 
                                description="Copy a file")
        self.server.register_tool("filesystem.delete_file", 
                                filesystem_tool.delete_file, 
                                description="Delete a file")
        
        # Terminal tools
        self.server.register_tool("terminal.execute_command", 
                                terminal_tool.execute_command, 
                                description="Execute a command in the terminal")
        self.server.register_tool("terminal.start_process", 
                                terminal_tool.start_process, 
                                description="Start a process")
        self.server.register_tool("terminal.terminate_process", 
                                terminal_tool.terminate_process, 
                                description="Terminate a process")
        
        # SSH tools
        self.server.register_tool("ssh.list_hosts", 
                                ssh_tool.ssh_list_hosts, 
                                description="List allowed SSH hosts")
        self.server.register_tool("ssh.connect", 
                                ssh_tool.ssh_connect, 
                                description="Check SSH connection to host")
        self.server.register_tool("ssh.execute", 
                                ssh_tool.ssh_execute, 
                                description="Execute a command on SSH host")
        self.server.register_tool("ssh.read_file", 
                                ssh_tool.ssh_read_file, 
                                description="Read file from SSH host")
        self.server.register_tool("ssh.write_file", 
                                ssh_tool.ssh_write_file, 
                                description="Write file to SSH host")
        self.server.register_tool("ssh.upload", 
                                ssh_tool.ssh_upload, 
                                description="Upload file to SSH host")
        self.server.register_tool("ssh.download", 
                                ssh_tool.ssh_download, 
                                description="Download file from SSH host")
        self.server.register_tool("ssh.disconnect", 
                                ssh_tool.ssh_disconnect, 
                                description="Close SSH connection")
        
        # Git tools
        self.server.register_tool("git.status", 
                                git_tool.git_status, 
                                description="Get Git status of a repository")
        self.server.register_tool("git.diff", 
                                git_tool.git_diff, 
                                description="Get Git diff of a repository")
        self.server.register_tool("git.log", 
                                git_tool.git_log, 
                                description="Get Git log of a repository")
        self.server.register_tool("git.branches", 
                                git_tool.git_branches, 
                                description="Get Git branches of a repository")
        self.server.register_tool("git.current_branch", 
                                git_tool.git_current_branch, 
                                description="Get current Git branch")
        self.server.register_tool("git.create_branch", 
                                git_tool.git_create_branch, 
                                description="Create a new Git branch")
        self.server.register_tool("git.add", 
                                git_tool.git_add, 
                                description="Add files to Git staging area")
        self.server.register_tool("git.commit", 
                                git_tool.git_commit, 
                                description="Commit staged files")
        self.server.register_tool("git.pull", 
                                git_tool.git_pull, 
                                description="Pull changes from remote origin")
        self.server.register_tool("git.push", 
                                git_tool.git_push, 
                                description="Push changes to remote origin")
        
        # Process tools
        self.server.register_tool("process.list", 
                                process_tool.list_processes, 
                                description="List running processes")
        self.server.register_tool("process.info", 
                                process_tool.get_process_info, 
                                description="Get information about a process")
        self.server.register_tool("process.kill", 
                                process_tool.kill_process, 
                                description="Kill a running process")
        
        # Systemd tools
        self.server.register_tool("systemd.status", 
                                systemd_tool.systemd_status, 
                                description="Get status of a systemd service")
        self.server.register_tool("systemd.logs", 
                                systemd_tool.systemd_logs, 
                                description="Get logs of a systemd service")
        self.server.register_tool("systemd.restart", 
                                systemd_tool.systemd_restart, 
                                description="Restart a systemd service")
        
        # Docker tools (optional)
        self.server.register_tool("docker.ps", 
                                docker_tool.docker_ps, 
                                description="List running Docker containers")
        self.server.register_tool("docker.logs", 
                                docker_tool.docker_logs, 
                                description="Get logs of a Docker container")
        self.server.register_tool("docker.inspect", 
                                docker_tool.docker_inspect, 
                                description="Inspect a Docker container")
        self.server.register_tool("docker.restart", 
                                docker_tool.docker_restart, 
                                description="Restart a Docker container")
        
        print("Registered all MCP tools")
        
    async def stop(self):
        """Stop the MCP server."""
        if self.server:
            await self.server.stop()
            print("Oleg Commander server stopped.")

# Main function for direct execution
async def main():
    """Main entry point."""
    config = Config()
    server = OlegCommanderServer(config)
    try:
        await server.start()
        # Keep the server running
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("Shutting down...")
        await server.stop()

if __name__ == "__main__":
    asyncio.run(main())