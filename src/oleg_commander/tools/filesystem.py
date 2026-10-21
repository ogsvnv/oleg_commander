"""MCP filesystem tools backed by no-follow, descriptor-relative operations."""

import asyncio
import errno
from pathlib import Path

from ..services.secure_filesystem import SecureFilesystem
from .base import ToolResult


class FilesystemTool:
    """Bounded filesystem operations confined to configured directories."""

    def __init__(self, security_manager):
        self.security_manager = security_manager

    @property
    def _filesystem(self) -> SecureFilesystem:
        return SecureFilesystem(
            self.security_manager.get_allowed_directories(),
            self.security_manager.config.execution.max_output_bytes,
        )

    def _error(self, exc: Exception) -> ToolResult:
        if isinstance(exc, (PermissionError, NotADirectoryError)) or (
            isinstance(exc, OSError) and exc.errno in (errno.ELOOP, errno.ENOTDIR)
        ):
            code, message = "FORBIDDEN", "Path or operation not permitted"
        elif isinstance(exc, FileNotFoundError):
            code, message = "NOT_FOUND", "Path does not exist"
        elif isinstance(exc, FileExistsError):
            code, message = "ALREADY_EXISTS", "Target already exists"
        elif isinstance(exc, (ValueError, UnicodeDecodeError)):
            code, message = "INVALID_ARGUMENT", str(exc)
        elif isinstance(exc, RuntimeError):
            code, message = "CONFLICT", "File changed during operation"
        else:
            code, message = "IO_ERROR", "Filesystem operation failed"
        return ToolResult(success=False, error={"code": code, "message": message})

    def _writable(self) -> bool:
        return self.security_manager.can_modify()

    @staticmethod
    def _locked() -> ToolResult:
        return ToolResult(
            success=False,
            error={"code": "READ_ONLY", "message": "Modification is not authorized"},
        )

    async def list_directory(self, path: str, depth: int = 1) -> ToolResult:
        try:
            items = await asyncio.to_thread(self._filesystem.list_dir, path, depth)
            return ToolResult(success=True, data={"items": items})
        except (OSError, ValueError, RuntimeError) as exc:
            return self._error(exc)

    async def read_file(
        self, path: str, offset: int = 0, limit: int | None = None
    ) -> ToolResult:
        if type(offset) is not int or offset < 0 or (
            limit is not None and (type(limit) is not int or limit < 0)
        ):
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Invalid offset or limit"},
            )
        try:
            data = await asyncio.to_thread(self._filesystem.read_bytes, path)
            text = data.decode("utf-8")
            text = text[offset:]
            if limit is not None:
                text = text[:limit]
            return ToolResult(success=True, data={"content": text})
        except (OSError, ValueError, UnicodeDecodeError, RuntimeError) as exc:
            return self._error(exc)

    async def read_multiple_files(self, paths: list[str]) -> ToolResult:
        if not isinstance(paths, list) or len(paths) > 20:
            return ToolResult(
                success=False,
                error={"code": "INVALID_ARGUMENT", "message": "Maximum 20 files per call"},
            )
        results = []
        total = 0
        for path in paths:
            try:
                data = await asyncio.to_thread(self._filesystem.read_bytes, path)
                total += len(data)
                if total > self._filesystem.max_bytes:
                    raise ValueError("Combined file size exceeds output limit")
                results.append({"path": path, "success": True, "content": data.decode("utf-8")})
            except (OSError, ValueError, UnicodeDecodeError, RuntimeError) as exc:
                result = self._error(exc)
                results.append({"path": path, "success": False, "error": result.error["code"]})
                if total > self._filesystem.max_bytes:
                    break
        return ToolResult(success=True, data={"results": results})

    async def write_file(self, path: str, content: str) -> ToolResult:
        if not self._writable():
            return self._locked()
        if not isinstance(content, str):
            return self._error(ValueError("Content must be text"))
        try:
            await asyncio.to_thread(self._filesystem.write_bytes, path, content.encode("utf-8"))
            return ToolResult(success=True, data={"message": "File written"})
        except (OSError, ValueError, RuntimeError) as exc:
            return self._error(exc)

    async def edit_file(self, path: str, old_text: str, new_text: str) -> ToolResult:
        if not self._writable():
            return self._locked()
        if not isinstance(old_text, str) or not isinstance(new_text, str):
            return self._error(ValueError("Replacement must be text"))
        try:
            changed = await asyncio.to_thread(
                self._filesystem.edit, path, old_text, new_text
            )
            if not changed:
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Old text not found"},
                )
            return ToolResult(success=True, data={"message": "File edited atomically"})
        except (OSError, ValueError, RuntimeError) as exc:
            return self._error(exc)

    async def search_files(self, path: str, pattern: str) -> ToolResult:
        try:
            files = await asyncio.to_thread(self._filesystem.search_files, path, pattern)
            return ToolResult(success=True, data={"files": files})
        except (OSError, ValueError, RuntimeError) as exc:
            return self._error(exc)

    async def search_content(self, path: str, query: str) -> ToolResult:
        try:
            files = await asyncio.to_thread(self._filesystem.search_content, path, query)
            return ToolResult(success=True, data={"files": files})
        except (OSError, ValueError, RuntimeError) as exc:
            return self._error(exc)

    async def get_file_info(self, path: str) -> ToolResult:
        try:
            info = await asyncio.to_thread(self._filesystem.file_info, path)
            return ToolResult(success=True, data={"info": info})
        except (OSError, ValueError, RuntimeError) as exc:
            return self._error(exc)

    async def create_directory(self, path: str) -> ToolResult:
        if not self._writable():
            return self._locked()
        try:
            await asyncio.to_thread(self._filesystem.mkdir, path)
            return ToolResult(success=True, data={"message": "Directory created"})
        except (OSError, ValueError, RuntimeError) as exc:
            return self._error(exc)

    async def move_file(self, source: str, destination: str) -> ToolResult:
        if not self._writable():
            return self._locked()
        try:
            await asyncio.to_thread(self._filesystem.move, source, destination)
            return ToolResult(success=True, data={"message": "File moved"})
        except (OSError, ValueError, RuntimeError) as exc:
            return self._error(exc)

    async def copy_file(self, source: str, destination: str) -> ToolResult:
        if not self._writable():
            return self._locked()
        try:
            await asyncio.to_thread(self._filesystem.copy, source, destination)
            return ToolResult(success=True, data={"message": "File copied"})
        except (OSError, ValueError, RuntimeError) as exc:
            return self._error(exc)

    async def delete_file(self, path: str) -> ToolResult:
        if not self._writable():
            return self._locked()
        try:
            await asyncio.to_thread(self._filesystem.delete, path)
            return ToolResult(success=True, data={"message": "File deleted"})
        except (OSError, ValueError, RuntimeError) as exc:
            return self._error(exc)
