"""Common result model shared by MCP tools and local services."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    """Structured data and error result of an MCP tool call."""

    success: bool
    data: dict[str, Any] | None = None
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the result to an MCP-serializable dictionary."""
        return {"success": self.success, "data": self.data, "error": self.error}
