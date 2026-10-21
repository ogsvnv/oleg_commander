"""Git repository actions through bounded subprocesses and verified cwd fds."""

import os
import re
from contextlib import contextmanager

from ..services.command_service import run_command
from ..services.secure_filesystem import SecureFilesystem
from .base import ToolResult

_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]{0,79}$")
_GIT_OPTIONS = (
    "git",
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.fsmonitor=false",
    "-c", "commit.gpgsign=false",
    "-c", "protocol.ext.allow=never",
    "-c", "protocol.file.allow=never",
    "--no-pager",
)


class GitTool:
    """Read and explicitly approved local Git operations.

    Remote pull/push are deliberately disabled pending separately validated
    origin remotes and SSH transport controls.
    """

    def __init__(self, security_manager):
        self.security_manager = security_manager

    @contextmanager
    def _repository(self, path: str):
        security = self.security_manager
        roots = security.get_allowed_directories()
        if not roots:
            raise PermissionError("No allowed Git directories")
        fs = SecureFilesystem(roots, security.config.execution.max_output_bytes)
        with fs.directory_fd(path) as (repo_fd, _):
            git_fd = os.open(
                ".git",
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=repo_fd,
            )
            try:
                yield repo_fd
            finally:
                os.close(git_fd)

    async def _run(self, path: str, *args: str) -> ToolResult:
        limits = self.security_manager.config.execution
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": os.path.expanduser("~"),
            "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
            "GIT_ASKPASS": "/bin/false",
        }
        try:
            with self._repository(path) as repo_fd:
                return await run_command(
                    [*_GIT_OPTIONS, *args],
                    timeout=limits.timeout,
                    max_output_bytes=limits.max_output_bytes,
                    cwd_fd=repo_fd,
                    env=env,
                )
        except (OSError, ValueError, PermissionError):
            return ToolResult(
                success=False,
                error={"code": "FORBIDDEN", "message": "Git repository path denied"},
            )

    @staticmethod
    def _field(result: ToolResult, field: str) -> ToolResult:
        if not result.success:
            return result
        return ToolResult(success=True, data={field: result.data["stdout"]})

    def _allow_write(self) -> ToolResult | None:
        if not self.security_manager.can_modify():
            return ToolResult(
                success=False,
                error={"code": "READ_ONLY", "message": "Git write not authorized"},
            )
        return None

    async def git_status(self, path: str) -> ToolResult:
        return self._field(
            await self._run(path, "status", "--porcelain=v1"), "status"
        )

    async def git_diff(self, path: str) -> ToolResult:
        return self._field(
            await self._run(path, "diff", "--no-ext-diff", "--no-textconv"), "diff"
        )

    async def git_log(self, path: str, limit: int = 10) -> ToolResult:
        if type(limit) is not int or not 1 <= limit <= 100:
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Limit must be 1–100"},
            )
        return self._field(
            await self._run(
                path, "log", f"--max-count={limit}", "--pretty=format:%h %an %s"
            ),
            "log",
        )

    async def git_branches(self, path: str) -> ToolResult:
        return self._field(
            await self._run(path, "branch", "--all", "--no-color"), "branches"
        )

    async def git_current_branch(self, path: str) -> ToolResult:
        result = await self._run(path, "branch", "--show-current")
        if not result.success:
            return result
        return ToolResult(
            success=True, data={"branch": result.data["stdout"].strip()}
        )

    async def git_create_branch(self, path: str, name: str) -> ToolResult:
        if denied := self._allow_write():
            return denied
        if not isinstance(name, str) or not _BRANCH.fullmatch(name) or (
            "//" in name or name.endswith(("/", ".lock"))
        ):
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Invalid branch name"},
            )
        result = await self._run(path, "branch", "--", name)
        return result if not result.success else ToolResult(
            success=True, data={"message": "Branch created"}
        )

    async def git_add(self, path: str, files: list[str]) -> ToolResult:
        if denied := self._allow_write():
            return denied
        if (
            not isinstance(files, list)
            or not 1 <= len(files) <= 40
            or any(
                not isinstance(name, str)
                or not name
                or len(name) > 256
                or name.startswith("-")
                or os.path.isabs(name)
                or ".." in name.split("/")
                or "\x00" in name
                for name in files
            )
        ):
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Invalid Git pathspec"},
            )
        result = await self._run(path, "add", "--", *files)
        return result if not result.success else ToolResult(
            success=True, data={"message": f"Staged {len(files)} pathspecs"}
        )

    async def git_commit(self, path: str, message: str) -> ToolResult:
        if denied := self._allow_write():
            return denied
        if (
            not isinstance(message, str)
            or not 1 <= len(message) <= 4000
            or "\x00" in message
        ):
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Invalid commit message"},
            )
        result = await self._run(
            path, "commit", "--no-verify", "--no-gpg-sign", "-m", message
        )
        return result if not result.success else ToolResult(
            success=True, data={"message": "Commit created"}
        )

    async def git_pull(self, path: str) -> ToolResult:
        if denied := self._allow_write():
            return denied
        return ToolResult(
            success=False,
            error={"code": "REMOTE_DISABLED", "message": "Git network sync unavailable"},
        )

    async def git_push(self, path: str) -> ToolResult:
        if denied := self._allow_write():
            return denied
        return ToolResult(
            success=False,
            error={"code": "REMOTE_DISABLED", "message": "Git network sync unavailable"},
        )
