"""Descriptor-relative Linux filesystem access beneath explicit allowlisted roots.

Every component is opened relative to an already opened directory fd with
O_NOFOLLOW, so symlink traversal is denied, including intermediate components.
All payloads, searches and directory listings are bounded.
"""

import fnmatch
import os
import stat
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_REGULAR = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_NEW_FILE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW


class SecureFilesystem:
    """Operate on paths beneath allowlisted roots without following symlinks."""

    def __init__(self, roots: list[Path], max_bytes: int):
        self.roots = sorted((Path(root).resolve() for root in roots), key=lambda p: -len(p.parts))
        self.max_bytes = max_bytes

    def _locate(self, path: str) -> tuple[Path, tuple[str, ...], Path]:
        if not isinstance(path, str) or not path or "\x00" in path:
            raise PermissionError("Invalid path")
        requested = Path(path).expanduser()
        if ".." in requested.parts:
            raise PermissionError("Parent traversal denied")
        absolute = Path(os.path.abspath(requested))
        for root in self.roots:
            if absolute.is_relative_to(root):
                return root, absolute.relative_to(root).parts, absolute
        raise PermissionError("Path outside configured directories")

    @contextmanager
    def directory_fd(self, path: str) -> Iterator[tuple[int, Path]]:
        root, parts, absolute = self._locate(path)
        fd = os.open(root, _DIRECTORY)
        try:
            for part in parts:
                child = os.open(part, _DIRECTORY, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd, absolute
        finally:
            os.close(fd)

    @contextmanager
    def parent_fd(self, path: str) -> Iterator[tuple[int, str, Path]]:
        root, parts, absolute = self._locate(path)
        if not parts:
            raise PermissionError("Cannot modify an allowlist root")
        fd = os.open(root, _DIRECTORY)
        try:
            for part in parts[:-1]:
                child = os.open(part, _DIRECTORY, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd, parts[-1], absolute
        finally:
            os.close(fd)

    @staticmethod
    def _stat_regular(fd: int, name: str) -> os.stat_result:
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise PermissionError("Regular files only; symbolic links denied")
        return info

    def _read_from_dir(self, parent_fd: int, name: str) -> tuple[bytes, os.stat_result]:
        file_fd = os.open(name, _REGULAR, dir_fd=parent_fd)
        try:
            info = os.fstat(file_fd)
            if not stat.S_ISREG(info.st_mode):
                raise PermissionError("Regular files only")
            if info.st_size > self.max_bytes:
                raise ValueError("File exceeds configured byte limit")
            data = bytearray()
            while len(data) <= self.max_bytes:
                chunk = os.read(file_fd, min(65536, self.max_bytes + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) > self.max_bytes:
                raise ValueError("File exceeds configured byte limit")
            return bytes(data), info
        finally:
            os.close(file_fd)

    def read_bytes(self, path: str) -> bytes:
        with self.parent_fd(path) as (parent, name, _):
            data, _ = self._read_from_dir(parent, name)
            return data

    def _atomic_replace(self, parent: int, name: str, content: bytes, expected=None):
        if len(content) > self.max_bytes:
            raise ValueError("Content exceeds configured byte limit")
        try:
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise PermissionError("Overwriting non-files and links is denied")
        if expected is not None and (
            current is None or
            (current.st_dev, current.st_ino, current.st_mtime_ns, current.st_size) != expected
        ):
            raise RuntimeError("File changed during edit")
        temporary = f".oleg-tmp-{uuid.uuid4().hex}"
        fd = os.open(temporary, _NEW_FILE, 0o600, dir_fd=parent)
        try:
            offset = 0
            while offset < len(content):
                offset += os.write(fd, content[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            # Rename changes only the directory entry and never follows the target.
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass

    def write_bytes(self, path: str, content: bytes):
        with self.parent_fd(path) as (parent, name, _):
            self._atomic_replace(parent, name, content)

    def edit(self, path: str, old: str, new: str) -> bool:
        if not old:
            raise ValueError("Replacement text must not be empty")
        with self.parent_fd(path) as (parent, name, _):
            data, info = self._read_from_dir(parent, name)
            text = data.decode("utf-8")
            if old not in text:
                return False
            replacement = text.replace(old, new).encode("utf-8")
            before = (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size)
            self._atomic_replace(parent, name, replacement, expected=before)
            return True

    def delete(self, path: str):
        with self.parent_fd(path) as (parent, name, _):
            self._stat_regular(parent, name)
            os.unlink(name, dir_fd=parent)

    def mkdir(self, path: str):
        root, parts, _ = self._locate(path)
        fd = os.open(root, _DIRECTORY)
        try:
            for part in parts:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(part, _DIRECTORY, dir_fd=fd)
                os.close(fd)
                fd = child
        finally:
            os.close(fd)

    def copy(self, source: str, destination: str):
        self.write_bytes(destination, self.read_bytes(source))

    def move(self, source: str, destination: str):
        with self.parent_fd(source) as (src_fd, src, _):
            self._stat_regular(src_fd, src)
            with self.parent_fd(destination) as (dst_fd, dst, _):
                try:
                    current = os.stat(dst, dir_fd=dst_fd, follow_symlinks=False)
                except FileNotFoundError:
                    current = None
                if current is not None and not stat.S_ISREG(current.st_mode):
                    raise PermissionError("Destination must be a regular file")
                os.rename(src, dst, src_dir_fd=src_fd, dst_dir_fd=dst_fd)
                os.fsync(dst_fd)

    def file_info(self, path: str) -> dict:
        with self.parent_fd(path) as (parent, name, absolute):
            info = self._stat_regular(parent, name)
            return {
                "path": str(absolute),
                "size": info.st_size,
                "is_directory": False,
                "is_file": True,
                "modified_time": info.st_mtime,
                "permissions": oct(stat.S_IMODE(info.st_mode)),
            }

    def list_dir(self, path: str, depth: int) -> list[dict]:
        if type(depth) is not int or not 1 <= depth <= 4:
            raise ValueError("Depth must be between 1 and 4")
        results = []
        for relative, info in self._walk(path, max_depth=depth):
            results.append({
                "name": relative.name,
                "path": str(relative),
                "is_directory": stat.S_ISDIR(info.st_mode),
                "size": info.st_size if stat.S_ISREG(info.st_mode) else 0,
            })
            if len(results) >= 250:
                break
        return results

    def _walk(self, path: str, max_depth: int = 5):
        """Yield only regular files and real directories, no symlinks."""
        started = time.monotonic()
        queue = [(path, 0)]
        seen = 0
        while queue:
            current, depth = queue.pop(0)
            with (
                self.directory_fd(current) as (directory, base),
                os.scandir(directory) as iterator,
            ):
                for entry in iterator:
                    if time.monotonic() - started > 3 or seen >= 2000:
                        return
                    seen += 1
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if not (
                        stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)
                    ):
                        continue
                    child = base / entry.name
                    yield child, info
                    if stat.S_ISDIR(info.st_mode) and depth + 1 < max_depth:
                        queue.append((str(child), depth + 1))

    def search_files(self, path: str, pattern: str) -> list[dict]:
        if not isinstance(pattern, str) or not pattern or len(pattern) > 128:
            raise ValueError("Invalid search pattern")
        matches = []
        for child, info in self._walk(path):
            if stat.S_ISREG(info.st_mode) and fnmatch.fnmatch(child.name, pattern):
                matches.append({"path": str(child), "name": child.name})
                if len(matches) >= 100:
                    break
        return matches

    def search_content(self, path: str, query: str) -> list[dict]:
        if not isinstance(query, str) or not 0 < len(query) <= 256:
            raise ValueError("Invalid search query")
        matches = []
        for child, info in self._walk(path):
            if not stat.S_ISREG(info.st_mode) or info.st_size > self.max_bytes:
                continue
            try:
                content = self.read_bytes(str(child)).decode("utf-8")
            except (PermissionError, FileNotFoundError, UnicodeDecodeError, ValueError, OSError):
                continue
            count = content.count(query)
            if count:
                matches.append({"path": str(child), "match_count": count})
                if len(matches) >= 100:
                    break
        return matches
