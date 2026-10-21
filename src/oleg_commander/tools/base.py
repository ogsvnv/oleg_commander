"""Base classes for MCP tools."""
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class ToolResult:
    """Standardized result format for MCP tools."""
    
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary format."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error
        }