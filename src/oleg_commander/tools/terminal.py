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
        # Safe, argument-free queries while mutations require approval.
        self._allowed_commands = {"pwd", "whoami", "uptime", "date", "uname"}

    async def execute_command(self, executable: str, args: List[str], 
                            cwd: Optional[str] = None, timeout: int = 30) -> ToolResult:
        """Execute a command in the terminal."""
        try:
            if cwd and not self.security_manager.is_path_allowed(cwd):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Working directory denied"},
                )
            # Check if command is allowed
            if not self._is_command_allowed(executable, args):
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
    
    def _is_command_allowed(self, command: str, args: List[str]) -> bool:
        """Prevent arbitrary code execution without an approval mechanism."""
        if not self.security_manager.can_modify():
            return command in self._allowed_commands and not args
        return True

    async def start_process(
        self,
        executable: str,
        args: List[str],
        cwd: Optional[str] = None,
    ) -> ToolResult:
        """Reject untracked processes until lifecycle controls are implemented."""
        return ToolResult(
            success=False,
            error={
                "code": "NOT_IMPLEMENTED",
                "message": "Background process management is unavailable",
            },
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
                success=False,
                error={"code": "NOT_IMPLEMENTED", "message": "Process termination unavailable"}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )