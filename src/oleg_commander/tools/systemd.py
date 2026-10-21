"""Restrict systemd operations to explicitly configured unit names."""

import re

from ..services.command_service import run_command
from .base import ToolResult

_SERVICE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}\.service$")


class SystemdTool:
    """Read systemd status/logs and restart allowlisted units when writable."""

    def __init__(self, security_manager):
        self.security_manager = security_manager

    def _validate(self, service: str) -> ToolResult | None:
        configured = self.security_manager.config.security.allowed_systemd_services
        if (
            not isinstance(service, str)
            or not _SERVICE_NAME.fullmatch(service)
            or service not in configured
        ):
            return ToolResult(
                success=False,
                error={"code": "FORBIDDEN", "message": "Service is not allowlisted"},
            )
        return None

    async def _run(self, *argv: str) -> ToolResult:
        limits = self.security_manager.config.execution
        return await run_command(
            argv,
            timeout=limits.timeout,
            max_output_bytes=limits.max_output_bytes,
        )

    async def systemd_status(self, service: str) -> ToolResult:
        """Return selected systemctl properties, not full unit configuration."""
        if denied := self._validate(service):
            return denied
        result = await self._run(
            "systemctl",
            "show",
            "--no-pager",
            "--property=Id,LoadState,ActiveState,SubState,MainPID",
            service,
        )
        if not result.success:
            return result
        values = {}
        for line in result.data["stdout"].splitlines():
            key, _, value = line.partition("=")
            if key in {"Id", "LoadState", "ActiveState", "SubState", "MainPID"}:
                values[key] = value
        return ToolResult(success=True, data={"service": service, "status": values})

    async def systemd_logs(self, service: str, lines: int = 100) -> ToolResult:
        """Read bounded recent journal entries for an allowlisted unit."""
        if denied := self._validate(service):
            return denied
        if type(lines) is not int or not 1 <= lines <= 1000:
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Invalid line count"},
            )
        result = await self._run(
            "journalctl",
            "--no-pager",
            "--output=short-iso",
            f"--unit={service}",
            f"--lines={lines}",
        )
        if not result.success:
            return result
        return ToolResult(
            success=True,
            data={"service": service, "logs": result.data["stdout"]},
        )

    async def systemd_restart(self, service: str) -> ToolResult:
        """Restart one allowlisted unit; no sudo or privilege elevation."""
        if denied := self._validate(service):
            return denied
        if not self.security_manager.can_modify():
            return ToolResult(
                success=False,
                error={"code": "READ_ONLY", "message": "Restart is not authorized"},
            )
        result = await self._run("systemctl", "restart", "--no-ask-password", service)
        if not result.success:
            return result
        return ToolResult(success=True, data={"service": service, "restarted": True})
