"""One-use out-of-band approvals bound to an exact MCP tool invocation.

The server creates requests; only the local CLI can approve them. SQLite
transactions make consumption atomic across concurrent server processes.
No raw tool arguments or file contents are persisted.
"""

import hashlib
import inspect
import json
import os
import sqlite3
import stat
import time
import uuid
from pathlib import Path
from typing import Any, Callable


def private_state_directory() -> Path:
    """Create one user-only state directory; reject insecure permissions."""
    directory = Path.home() / ".local" / "state" / "oleg-commander"
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise PermissionError("Insecure state directory")
    if stat.S_IMODE(directory.stat().st_mode) & 0o077:
        raise PermissionError("State directory must be private (0700)")
    return directory


def private_file(path: Path) -> Path:
    """Create state file without following symlinks, with mode 0600."""
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.parent.is_symlink() or stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
        raise PermissionError("State parent directory must be private")
    fd = os.open(str(path), os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    if not stat.S_ISREG(path.stat().st_mode) or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError("State file must be a regular private file (0600)")
    return path


def invocation_digest(name: str, fn: Callable[..., Any], args: tuple, kwargs: dict) -> str:
    """Digest canonical arguments including parameter defaults, not their values in DB."""
    bound = inspect.signature(fn).bind(*args, **kwargs)
    bound.apply_defaults()
    payload = json.dumps(
        [name, bound.arguments], ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def safe_target(fn: Callable[..., Any], args: tuple, kwargs: dict) -> str:
    """Summarize non-content target fields without persisting credentials."""
    bound = inspect.signature(fn).bind(*args, **kwargs)
    selected = []
    for key, value in bound.arguments.items():
        if key in ("path", "source", "destination", "local_path", "remote_path",
                   "host", "service", "container", "executable", "pid", "name") and isinstance(value, (str, int)):
            display = str(value).replace("\n", " ").replace("\r", " ")[:160]
            selected.append(f"{key}={display}")
    return ", ".join(selected)[:400] or "(no visible target)"


class ApprovalService:
    """Store pending requests and consume approved requests exactly once."""

    def __init__(self, db_path: str | Path | None = None, timeout_minutes: int = 10):
        self.path = Path(db_path) if db_path else private_state_directory() / "approvals.sqlite3"
        private_file(self.path)
        self.timeout = timeout_minutes * 60
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    tool TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    target TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created REAL NOT NULL,
                    expires REAL NOT NULL
                )"""
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_approval_lookup ON approvals(tool, digest, status, expires)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def request_or_consume(
        self, tool: str, fn: Callable[..., Any], args: tuple, kwargs: dict
    ) -> tuple[bool, str]:
        """Return (authorized, id); otherwise create/reuse a pending request."""
        digest = invocation_digest(tool, fn, args, kwargs)
        target = safe_target(fn, args, kwargs)
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE approvals SET status='expired' WHERE status IN ('pending','approved') AND expires<=?",
                (now,),
            )
            row = db.execute(
                "SELECT id FROM approvals WHERE tool=? AND digest=? AND status='approved' AND expires>? ORDER BY created LIMIT 1",
                (tool, digest, now),
            ).fetchone()
            if row:
                db.execute("UPDATE approvals SET status='consumed' WHERE id=? AND status='approved'", (row[0],))
                return True, row[0]
            row = db.execute(
                "SELECT id FROM approvals WHERE tool=? AND digest=? AND status='pending' AND expires>? ORDER BY created LIMIT 1",
                (tool, digest, now),
            ).fetchone()
            if row:
                return False, row[0]
            request_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO approvals(id,tool,digest,target,status,created,expires) VALUES(?,?,?,?,?,?,?)",
                (request_id, tool, digest, target, "pending", now, now + self.timeout),
            )
            return False, request_id

    def decide(self, request_id: str, approve: bool) -> bool:
        """For local CLI only. Cannot approve expired or used requests."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                "UPDATE approvals SET status=? WHERE id=? AND status='pending' AND expires>?",
                ("approved" if approve else "rejected", request_id, time.time()),
            )
            return cursor.rowcount == 1

    def list_requests(self, limit: int = 30) -> list[dict[str, Any]]:
        """Show pending/approved requests to the local CLI, without secrets."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT id,tool,target,digest,status,expires FROM approvals "
                "WHERE status IN ('pending','approved') AND expires>? "
                "ORDER BY created DESC LIMIT ?",
                (time.time(), min(max(1, limit), 100)),
            ).fetchall()
        return [
            {"id": row[0], "tool": row[1], "target": row[2],
             "digest": row[3], "status": row[4], "expires": row[5]}
            for row in rows
        ]
