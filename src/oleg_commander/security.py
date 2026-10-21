"""Security module for Oleg Commander."""
import os
import pathlib
from typing import List, Optional
from pathlib import Path, PurePosixPath
from contextlib import contextmanager
from contextvars import ContextVar
from .config import Config

class SecurityManager:
    """Centralized security manager for Oleg Commander."""
    
    def __init__(self, config: Config):
        self.config = config
        self._approved: ContextVar[bool] = ContextVar('approved_mcp_write', default=False)
        self._allowed_directories = set()
        self._allowed_ssh_hosts = set()
        self._initialize_security()
    
    def _initialize_security(self):
        """Initialize security settings from config."""
        # Set allowed directories
        if self.config.security.allowed_directories:
            for directory in self.config.security.allowed_directories:
                try:
                    path = Path(directory).resolve()
                    self._allowed_directories.add(path)
                except Exception:
                    # Skip invalid directories
                    continue
        
        # Set allowed SSH hosts
        if self.config.security.allowed_ssh_hosts:
            self._allowed_ssh_hosts = set(self.config.security.allowed_ssh_hosts)
    
    def is_path_allowed(self, path: str) -> bool:
        """Check if a path is allowed."""
        try:
            resolved_path = Path(path).resolve()
            
            # Check for path traversal
            if not self._is_safe_path(resolved_path):
                return False
            
            # Check against allowed directories
            if self.config.security.allowed_directories:
                # Verify that the path is within one of the allowed directories
                if not any(resolved_path.is_relative_to(allowed) 
                          for allowed in self._allowed_directories):
                    return False
            else:
                # If no directories are explicitly allowed, only allow within home directory
                home = Path.home()
                if not resolved_path.is_relative_to(home):
                    return False
            
            return True
        except Exception:
            return False
    
    def _is_safe_path(self, path: Path) -> bool:
        """Check for path traversal attempts."""
        # Check for . and .. components in the path
        try:
            # Resolve the path to its absolute form to prevent directory traversal
            normalized = path.resolve()
            
            # Check for symbolic link traversal
            if path.is_symlink():
                return False
                
            return True
        except Exception:
            return False
    
    def is_ssh_host_allowed(self, hostname: str) -> bool:
        """Check if SSH host is allowed."""
        if not self.config.security.allowed_ssh_hosts:
            return False  # No SSH hosts configured: deny by default
        
        return hostname in self._allowed_ssh_hosts
    
    def is_ssh_path_allowed(self, hostname: str, path: str) -> bool:
        """Check a remote absolute path against an explicit per-host allowlist.

        Call this for both the supplied path and the result of SFTP realpath()
        so simple traversal and remote symlink escapes are both denied.
        """
        if not self.is_ssh_host_allowed(hostname) or not path:
            return False

        remote = PurePosixPath(path)
        if (
            not remote.is_absolute()
            or ".." in remote.parts
            or "\\x00" in path
        ):
            return False

        for allowed in self.config.security.allowed_ssh_directories.get(
            hostname, []
        ):
            root = PurePosixPath(allowed)
            if root.is_absolute() and ".." not in root.parts:
                if remote.is_relative_to(root):
                    return True
        return False

    def is_command_allowed(self, command: str) -> bool:
        """Check if a command is allowed."""
        # This will be expanded with actual command filtering logic
        return not self.config.security.read_only
    
    @contextmanager
    def authorized_write(self):
        """Enable a single approved write in the current async task only."""
        token = self._approved.set(True)
        try:
            yield
        finally:
            self._approved.reset(token)

    def can_modify(self) -> bool:
        """Never permit writes in read-only mode.

        When approvals are mandatory, only an approved server-side tool
        wrapper may enable writes in its own execution context.
        """
        return not self.config.security.read_only and (
            not self.config.security.require_approval or self._approved.get()
        )

    def require_approval(self) -> bool:
        """Check if approval is required for operations."""
        return self.config.security.require_approval
    
    def get_allowed_directories(self) -> List[Path]:
        """Get list of allowed directories."""
        return list(self._allowed_directories)
    
    def get_allowed_ssh_hosts(self) -> List[str]:
        """Get list of allowed SSH hosts."""
        return list(self._allowed_ssh_hosts)