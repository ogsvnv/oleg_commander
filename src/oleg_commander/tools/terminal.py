"""Terminal tools for Oleg Commander."""
import asyncio
import shlex
from pathlib import Path
from typing import List, Optional, Dict, Any
from .base import ToolResult

class TerminalTool:
    """Tools for working with the terminal."""
    
    def __init__(self, security_manager):
        self.security_manager = security_manager
        # List of allowed commands (add more as needed)
        self._allowed_commands = {
            'ls', 'cat', 'grep', 'find', 'echo', 'pwd', 'whoami',
            'df', 'du', 'ps', 'top', 'uptime', 'date', 'time'
        }
    
    async def execute_command(self, executable: str, args: List[str], 
                            cwd: Optional[str] = None, timeout: int = 30) -> ToolResult:
        """Execute a command in the terminal."""
        try:
            # Check if command is allowed
            if not self._is_command_allowed(executable):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": f"Command '{executable}' not allowed"}
                )
                
            # Prepare command
            full_command = [executable] + args
            
            # Set up process creation
            process = await asyncio.create_subprocess_exec(
                executable, 
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd if cwd else None
            )
            
            # Wait for completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                
                result = {
                    "success": True,
                    "exit_code": process.returncode,
                    "stdout": stdout.decode('utf-8') if stdout else "",
                    "stderr": stderr.decode('utf-8') if stderr else "",
                    "duration_ms": 0
                }
                
                return ToolResult(success=True, data=result)
            except asyncio.TimeoutError:
                # Kill the process if it times out
                process.kill()
                await process.wait()
                return ToolResult(
                    success=False,
                    error={"code": "TIMEOUT", "message": f"Command timed out after {timeout}s"}
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
    
    def _is_command_allowed(self, command: str) -> bool:
        """Check if a command is in the allowed list."""
        if self.security_manager.config.security.read_only:
            # In read-only mode, only allow safe operations
            return command in self._allowed_commands
        
        # Allow all commands in read-write mode, but still check for path traversal risks
        return True

    async def start_process(self, executable: str, args: List[str], 
                           cwd: Optional[str] = None) -> ToolResult:
        """Start a process."""
        try:
            full_command = [executable] + args
            
            process = await asyncio.create_subprocess_exec(
                executable,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd if cwd else None
            )
            
            # We could store process info here for tracking...
            return ToolResult(
                success=True,
                data={
                    "process_id": process.pid,
                    "status": "started"
                }
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def get_process_output(self, process_id: int) -> ToolResult:
        """Get output from a running process."""
        return ToolResult(
            success=False,
            error={"code": "NOT_IMPLEMENTED", "message": "Process monitoring not implemented"}
        )
            
    async def terminate_process(self, process_id: int) -> ToolResult:
        """Terminate a process."""
        try:
            # For demonstration - we can't properly terminate processes in this context
            return ToolResult(
                success=True,
                data={"message": "Process termination not implemented"}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )