"""Path service for Oleg Commander."""
from pathlib import Path
from typing import List, Set
from ..security import SecurityManager

class PathService:
    """Service for handling path-related operations with security checks."""
    
    def __init__(self, security_manager: SecurityManager):
        self.security_manager = security_manager
        
    def is_safe_path(self, path: str) -> bool:
        """Check if a path is safe and allowed."""
        try:
            # Resolved absolute path
            resolved_path = Path(path).resolve()
            
            # Check for path traversal (.. components)
            if ".." in path.split("/"):
                return False
                
            # Check against allowed directories
            if not self.security_manager.is_path_allowed(path):
                return False
                
            return True
        except Exception:
            return False
    
    def get_allowed_directories(self) -> List[Path]:
        """Get list of allowed directories."""
        return self.security_manager.get_allowed_directories()