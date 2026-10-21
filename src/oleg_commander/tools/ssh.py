"""AsyncSSH operations with host verification and explicit path boundaries."""

import asyncio
import shlex
from pathlib import Path
from uuid import uuid4

import asyncssh

from .base import ToolResult


class SSHTool:
    """Perform stateless SSH and SFTP operations against approved hosts."""

    READ_ONLY_COMMANDS = frozenset(
        {"date", "hostname", "pwd", "uname", "uptime", "whoami"}
    )

    def __init__(self, security_manager):
        self.security_manager = security_manager

    @property
    def _limits(self):
        return self.security_manager.config.execution

    def _connection(self, host):
        # Never disable verification: even a configured SSH alias must have
        # a trusted entry in the local user's OpenSSH known_hosts file.
        return asyncssh.connect(
            host,
            known_hosts=str(Path.home() / ".ssh" / "known_hosts"),
            connect_timeout=self._limits.timeout,
        )

    def _host_denied(self, host):
        if not self.security_manager.is_ssh_host_allowed(host):
            return ToolResult(
                success=False,
                error={"code": "FORBIDDEN", "message": f"SSH host '{host}' denied"},
            )
        return None

    def _write_denied(self):
        if not self.security_manager.can_modify():
            return ToolResult(
                success=False,
                error={"code": "READ_ONLY", "message": "Writes need explicit permission"},
            )
        return None

    def _failure(self, exc):
        if isinstance(exc, TimeoutError):
            code = "TIMEOUT"
        elif isinstance(exc, PermissionError):
            code = "FORBIDDEN"
        elif isinstance(exc, UnicodeDecodeError):
            code = "INVALID_ENCODING"
        elif isinstance(exc, (asyncssh.Error, OSError)):
            code = "SSH_ERROR"
        else:
            code = "UNKNOWN_ERROR"
        return ToolResult(
            success=False,
            error={"code": code, "message": str(exc)},
        )

    async def _checked_path(self, sftp, host, path):
        """Verify both user-supplied and canonical paths (resolves symlinks)."""
        if not self.security_manager.is_ssh_path_allowed(host, path):
            raise PermissionError("Remote path is outside permitted directories")
        canonical = await sftp.realpath(path)
        if not self.security_manager.is_ssh_path_allowed(host, canonical):
            raise PermissionError("Remote path resolves outside permitted directories")
        return canonical

    async def _read_remote(self, host, path):
        async with (
            self._connection(host) as conn,
            conn.start_sftp_client() as sftp,
        ):
            canonical = await self._checked_path(sftp, host, path)
            async with sftp.open(canonical, "rb") as remote_file:
                data = await remote_file.read(self._limits.max_output_bytes + 1)
            if len(data) > self._limits.max_output_bytes:
                raise ValueError("Remote file exceeds configured size limit")
            return data

    async def _write_remote(self, host, path, content):
        """Write through a unique file and an atomic POSIX rename."""
        if len(content) > self._limits.max_output_bytes:
            raise ValueError("Content exceeds configured size limit")

        async with (
            self._connection(host) as conn,
            conn.start_sftp_client() as sftp,
        ):
            canonical = await self._checked_path(sftp, host, path)
            temporary = f"{canonical}.oleg-commander-{uuid4().hex}"
            if not self.security_manager.is_ssh_path_allowed(host, temporary):
                raise PermissionError("Temporary path outside permitted directories")
            try:
                async with sftp.open(temporary, "xb") as remote_file:
                    await remote_file.write(content)
                # Explicit POSIX rename support is required. No unsafe
                # in-place overwrite fallback is attempted.
                await sftp.posix_rename(temporary, canonical)
            except Exception:
                try:
                    await sftp.remove(temporary)
                except (OSError, asyncssh.Error):
                    pass
                raise

    async def ssh_list_hosts(self) -> ToolResult:
        return ToolResult(
            success=True,
            data={"hosts": sorted(self.security_manager.get_allowed_ssh_hosts())},
        )

    async def ssh_connect(self, host: str) -> ToolResult:
        """Open, authenticate, verify the host key and close the connection."""
        if denied := self._host_denied(host):
            return denied
        try:
            async with self._connection(host):
                return ToolResult(
                    success=True,
                    data={"host": host, "verified": True, "connected": True},
                )
        except (asyncssh.Error, OSError, TimeoutError) as exc:
            return self._failure(exc)

    async def ssh_execute(
        self, host: str, executable: str, args: list[str], timeout: int = 30
    ) -> ToolResult:
        """Run a remote command without shell interpolation of arguments."""
        if denied := self._host_denied(host):
            return denied
        if not isinstance(executable, str) or not executable or not isinstance(args, list):
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Invalid command"},
            )
        if not all(isinstance(arg, str) for arg in args):
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Arguments must be strings"},
            )
        if (
            not self.security_manager.can_modify()
            and (executable not in self.READ_ONLY_COMMANDS or args)
        ):
            return ToolResult(
                success=False,
                error={"code": "FORBIDDEN", "message": "Unsafe SSH command denied"},
            )
        if not isinstance(timeout, int) or timeout <= 0:
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Invalid timeout"},
            )

        effective_timeout = min(timeout, self._limits.timeout)
        command = shlex.join([executable, *args])
        try:
            async with self._connection(host) as conn:
                result = await asyncio.wait_for(
                    conn.run(command, check=False), timeout=effective_timeout
                )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            if (
                len(stdout.encode("utf-8")) + len(stderr.encode("utf-8"))
                > self._limits.max_output_bytes
            ):
                return ToolResult(
                    success=False,
                    error={"code": "OUTPUT_LIMIT", "message": "Command output too large"},
                )
            data = {
                "host": host,
                "exit_code": result.exit_status,
                "stdout": stdout,
                "stderr": stderr,
            }
            if result.exit_status != 0:
                return ToolResult(
                    success=False,
                    data=data,
                    error={"code": "NON_ZERO_EXIT", "message": "Remote command failed"},
                )
            return ToolResult(success=True, data=data)
        except (asyncssh.Error, OSError, TimeoutError) as exc:
            return self._failure(exc)

    async def ssh_read_file(self, host: str, path: str) -> ToolResult:
        """Read a bounded UTF-8 file from an approved remote directory."""
        if denied := self._host_denied(host):
            return denied
        if not self.security_manager.is_ssh_path_allowed(host, path):
            return self._failure(PermissionError("Remote path denied"))
        try:
            content = await asyncio.wait_for(
                self._read_remote(host, path), timeout=self._limits.timeout
            )
            return ToolResult(
                success=True,
                data={"host": host, "path": path, "content": content.decode("utf-8")},
            )
        except (asyncssh.Error, OSError, TimeoutError,
                PermissionError, UnicodeDecodeError, ValueError) as exc:
            return self._failure(exc)

    async def ssh_write_file(self, host: str, path: str, content: str) -> ToolResult:
        """Write via SFTP only when security explicitly permits mutations."""
        if denied := self._host_denied(host):
            return denied
        if denied := self._write_denied():
            return denied
        if not self.security_manager.is_ssh_path_allowed(host, path):
            return self._failure(PermissionError("Remote path denied"))
        try:
            data = content.encode("utf-8")
            await asyncio.wait_for(
                self._write_remote(host, path, data), timeout=self._limits.timeout
            )
            return ToolResult(success=True, data={"host": host, "path": path})
        except (asyncssh.Error, OSError, TimeoutError,
                PermissionError, ValueError) as exc:
            return self._failure(exc)

    async def ssh_upload(self, host: str, local_path: str, remote_path: str) -> ToolResult:
        """Copy one bounded local file to an allowed remote directory."""
        if denied := self._host_denied(host):
            return denied
        if denied := self._write_denied():
            return denied
        if not (
            self.security_manager.is_path_allowed(local_path)
            and self.security_manager.is_ssh_path_allowed(host, remote_path)
        ):
            return self._failure(PermissionError("Transfer path denied"))
        try:
            source = Path(local_path)
            if source.stat().st_size > self._limits.max_output_bytes:
                raise ValueError("Local file exceeds configured size limit")
            data = source.read_bytes()
            await asyncio.wait_for(
                self._write_remote(host, remote_path, data),
                timeout=self._limits.timeout,
            )
            return ToolResult(success=True, data={"bytes": len(data)})
        except (asyncssh.Error, OSError, TimeoutError,
                PermissionError, ValueError) as exc:
            return self._failure(exc)

    @staticmethod
    def _save_new_local_file(local_path: str, data: bytes) -> None:
        """Exclusively create the download target without blocking the loop."""
        with Path(local_path).open("xb") as destination:
            destination.write(data)

    async def ssh_download(self, host: str, remote_path: str, local_path: str) -> ToolResult:
        """Download without overwriting an existing local file."""
        if denied := self._host_denied(host):
            return denied
        if denied := self._write_denied():
            return denied
        if not (
            self.security_manager.is_path_allowed(local_path)
            and self.security_manager.is_ssh_path_allowed(host, remote_path)
        ):
            return self._failure(PermissionError("Transfer path denied"))
        try:
            data = await asyncio.wait_for(
                self._read_remote(host, remote_path), timeout=self._limits.timeout
            )
            # Exclusive create prevents clobbering existing files and symlinks.
            await asyncio.to_thread(self._save_new_local_file, local_path, data)
            return ToolResult(success=True, data={"bytes": len(data)})
        except (asyncssh.Error, OSError, TimeoutError,
                PermissionError, ValueError) as exc:
            return self._failure(exc)

    async def ssh_disconnect(self, host: str) -> ToolResult:
        """Connections are scoped to each request and automatically closed."""
        if denied := self._host_denied(host):
            return denied
        return ToolResult(
            success=True,
            data={"host": host, "connected": False, "message": "Stateless connection"},
        )
