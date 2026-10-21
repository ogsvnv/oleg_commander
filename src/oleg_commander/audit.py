"""Structured, privacy-preserving JSONL audit of MCP tool invocations.

No arguments, command output, file contents, tokens, or credentials are logged.
The file and its directory are accessible only to the local user.
"""

import json
import os
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from .services.approval_service import private_file, private_state_directory


class AuditLogger:
    """Append minimal outcome metadata to a private local audit log."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else private_state_directory() / "audit.jsonl"
        private_file(self.path)

    def record(
        self, *, tool: str, status: str, request_id: str | None = None,
        error_code: str | None = None, duration_ms: int = 0,
    ) -> None:
        """Append an event, without raw arguments or response contents."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "status": status,
            "request_id": request_id,
            "error_code": error_code,
            "duration_ms": duration_ms,
        }
        encoded = (json.dumps(entry, sort_keys=True) + "\n").encode("utf-8")
        fd = os.open(str(self.path), os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        try:
            os.write(fd, encoded)
            os.fsync(fd)
        finally:
            os.close(fd)

    def recent(self, limit: int = 30) -> list[dict]:
        """Fetch recent events for the local CLI only."""
        with self.path.open(encoding="utf-8") as stream:
            items = deque(stream, maxlen=min(max(limit, 1), 100))
        return [json.loads(line) for line in items]
