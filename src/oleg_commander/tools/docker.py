"""Docker diagnostics with explicit container allowlists and safe fields."""

import json
import re

from ..services.command_service import run_command
from .base import ToolResult

_CONTAINER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class DockerTool:
    """Restrict Docker API visibility and mutations to allowed containers."""

    def __init__(self, security_manager):
        self.security_manager = security_manager

    @property
    def _allowed(self) -> set[str]:
        return set(self.security_manager.config.security.allowed_docker_containers)

    def _validate(self, container: str) -> ToolResult | None:
        if (
            not isinstance(container, str)
            or not _CONTAINER_NAME.fullmatch(container)
            or container not in self._allowed
        ):
            return ToolResult(
                success=False,
                error={"code": "FORBIDDEN", "message": "Container is not allowlisted"},
            )
        return None

    async def _run(self, *argv: str) -> ToolResult:
        limits = self.security_manager.config.execution
        return await run_command(
            argv,
            timeout=limits.timeout,
            max_output_bytes=limits.max_output_bytes,
        )

    async def docker_ps(self) -> ToolResult:
        """List only explicitly approved containers, omitting command/env data."""
        if not self._allowed:
            return ToolResult(success=True, data={"containers": []})
        result = await self._run("docker", "ps", "--all", "--format", "{{json .}}")
        if not result.success:
            return result
        containers = []
        try:
            for row in result.data["stdout"].splitlines():
                info = json.loads(row)
                names = info.get("Names", "").split(",")
                if any(name in self._allowed for name in names):
                    containers.append(
                        {
                            "id": info.get("ID"),
                            "names": [name for name in names if name in self._allowed],
                            "image": info.get("Image"),
                            "status": info.get("Status"),
                            "state": info.get("State"),
                        }
                    )
        except (ValueError, AttributeError) as exc:
            return ToolResult(
                success=False,
                error={"code": "INVALID_OUTPUT", "message": str(exc)},
            )
        return ToolResult(success=True, data={"containers": containers})

    async def docker_logs(self, container: str, lines: int = 100) -> ToolResult:
        """Fetch bounded logs for one allowlisted container."""
        if denied := self._validate(container):
            return denied
        if type(lines) is not int or not 1 <= lines <= 1000:
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Invalid line count"},
            )
        result = await self._run(
            "docker", "logs", "--tail", str(lines), "--", container
        )
        if not result.success:
            return result
        return ToolResult(
            success=True,
            data={
                "container": container,
                "stdout": result.data["stdout"],
                "stderr": result.data["stderr"],
            },
        )

    async def docker_inspect(self, container: str) -> ToolResult:
        """Report a projection without secrets such as environment variables."""
        if denied := self._validate(container):
            return denied
        result = await self._run(
            "docker",
            "inspect",
            "--format",
            "{{json .Name}}|{{json .Config.Image}}|{{json .State.Status}}",
            "--",
            container,
        )
        if not result.success:
            return result
        try:
            name, image, state = (
                json.loads(value)
                for value in result.data["stdout"].strip().split("|")
            )
        except (ValueError, TypeError) as exc:
            return ToolResult(
                success=False,
                error={"code": "INVALID_OUTPUT", "message": str(exc)},
            )
        return ToolResult(
            success=True,
            data={"container": container, "name": name, "image": image, "state": state},
        )

    async def docker_restart(self, container: str) -> ToolResult:
        """Restart an allowlisted container with explicit write permission."""
        if denied := self._validate(container):
            return denied
        if not self.security_manager.can_modify():
            return ToolResult(
                success=False,
                error={"code": "READ_ONLY", "message": "Restart is not authorized"},
            )
        result = await self._run("docker", "restart", "--", container)
        if not result.success:
            return result
        return ToolResult(
            success=True, data={"container": container, "restarted": True}
        )
