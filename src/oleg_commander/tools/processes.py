"""Read-only process diagnostics without exposing command arguments."""

from ..services.command_service import run_command
from .base import ToolResult


class ProcessTool:
    """List processes and inspect numeric PIDs without revealing env/argv."""

    def __init__(self, security_manager):
        self.security_manager = security_manager

    async def _run(self, *argv: str) -> ToolResult:
        limits = self.security_manager.config.execution
        return await run_command(
            argv,
            timeout=limits.timeout,
            max_output_bytes=limits.max_output_bytes,
        )

    @staticmethod
    def _parse(stdout: str) -> list[dict]:
        entries = []
        for line in stdout.splitlines():
            fields = line.split(maxsplit=4)
            if len(fields) != 5:
                continue
            pid, ppid, state, elapsed, name = fields
            entries.append(
                {
                    "pid": int(pid),
                    "ppid": int(ppid),
                    "state": state,
                    "elapsed": elapsed,
                    "name": name,
                }
            )
        return entries

    async def list_processes(self) -> ToolResult:
        """List bounded process metadata, never sensitive command arguments."""
        result = await self._run("ps", "-eo", "pid=,ppid=,stat=,etime=,comm=")
        if not result.success:
            return result
        try:
            processes = self._parse(result.data["stdout"])
        except ValueError:
            return ToolResult(
                success=False,
                error={"code": "INVALID_OUTPUT", "message": "Unexpected ps output"},
            )
        return ToolResult(success=True, data={"processes": processes})

    async def get_process_info(self, pid: int) -> ToolResult:
        """Read selected metadata for one numeric process ID."""
        if type(pid) is not int or pid <= 0:
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Invalid PID"},
            )
        result = await self._run(
            "ps", "-p", str(pid), "-o", "pid=,ppid=,stat=,etime=,comm="
        )
        if not result.success:
            return result
        try:
            processes = self._parse(result.data["stdout"])
        except ValueError:
            return ToolResult(
                success=False,
                error={"code": "INVALID_OUTPUT", "message": "Unexpected ps output"},
            )
        if not processes:
            return ToolResult(
                success=False,
                error={"code": "NOT_FOUND", "message": "Process not found"},
            )
        return ToolResult(success=True, data=processes[0])

    async def kill_process(self, pid: int) -> ToolResult:
        """Signal delivery remains disabled until interactive approval exists."""
        return ToolResult(
            success=False,
            error={"code": "NOT_IMPLEMENTED", "message": "Process killing unavailable"},
        )
