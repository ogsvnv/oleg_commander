"""Local terminal with bounded execution and descriptor-safe working directories."""

import os
import re

from ..services.command_service import run_command
from ..services.secure_filesystem import SecureFilesystem
from .base import ToolResult

_EXECUTABLE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.+-]{0,63}$")


class TerminalTool:
    """Execute safe diagnostics or independently approved commands."""

    READ_ONLY_COMMANDS = frozenset({"pwd", "whoami", "uptime", "date", "uname"})

    def __init__(self, security_manager):
        self.security_manager = security_manager
        self._allowed_commands = self.READ_ONLY_COMMANDS

    async def execute_command(
        self,
        executable: str,
        args: list[str],
        cwd: str | None = None,
        timeout: int | None = None,
    ) -> ToolResult:
        """Run a validated executable without a shell, within an approved root."""
        limits = self.security_manager.config.execution
        if (
            not isinstance(executable, str)
            or not _EXECUTABLE.fullmatch(executable)
            or not isinstance(args, list)
            or len(args) > 32
            or any(
                not isinstance(arg, str)
                or len(arg) > 2048
                or "\x00" in arg
                for arg in args
            )
            or sum(len(arg) for arg in args) > 8192
        ):
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Invalid command/arguments"},
            )
        if timeout is not None and (
            type(timeout) is not int
            or timeout < 1
            or timeout > limits.timeout
        ):
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Invalid timeout"},
            )
        if not self.security_manager.can_modify() and (
            executable not in self.READ_ONLY_COMMANDS or bool(args)
        ):
            return ToolResult(
                success=False,
                error={"code": "FORBIDDEN", "message": "Command needs approval"},
            )
        roots = self.security_manager.get_allowed_directories()
        if not roots:
            return ToolResult(
                success=False,
                error={"code": "FORBIDDEN", "message": "No allowed directories"},
            )
        directory = cwd if cwd is not None else str(roots[0])
        filesystem = SecureFilesystem(roots, limits.max_output_bytes)
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": os.path.expanduser("~"),
            "LANG": "C.UTF-8",
        }
        try:
            with filesystem.directory_fd(directory) as (fd, _):
                return await run_command(
                    [executable, *args],
                    timeout=timeout if timeout is not None else limits.timeout,
                    max_output_bytes=limits.max_output_bytes,
                    cwd_fd=fd,
                    env=env,
                )
        except (OSError, ValueError, PermissionError):
            return ToolResult(
                success=False,
                error={"code": "FORBIDDEN", "message": "Working directory denied"},
            )

    async def start_process(
        self, executable: str, args: list[str], cwd: str | None = None
    ) -> ToolResult:
        """Persistent process execution requires lifecycle and safety controls."""
        return ToolResult(
            success=False,
            error={"code": "NOT_IMPLEMENTED", "message": "Background processes unavailable"},
        )

    async def get_process_output(self, process_id: int) -> ToolResult:
        return ToolResult(
            success=False,
            error={"code": "NOT_IMPLEMENTED", "message": "Background processes unavailable"},
        )

    async def terminate_process(self, process_id: int) -> ToolResult:
        return ToolResult(
            success=False,
            error={"code": "NOT_IMPLEMENTED", "message": "Background processes unavailable"},
        )
