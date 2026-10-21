"""Git tools for Oleg Commander."""
import asyncio
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any
from .base import ToolResult

class GitTool:
    """Tools for working with Git repositories."""
    
    def __init__(self, security_manager):
        self.security_manager = security_manager
        
    async def git_status(self, path: str) -> ToolResult:
        """Get Git status of a repository."""
        try:
            # Validate path is allowed
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            repo_path = Path(path)
            if not repo_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Repository not found"}
                )
                
            # Verify it's a git repository
            if not (repo_path / ".git").exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_GIT_REPO", "message": "Path is not a Git repository"}
                )
                
            # Run git status (async)
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return ToolResult(
                success=True,
                data={"status": result.stdout}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error={"code": "TIMEOUT", "message": "Git command timed out"}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def git_diff(self, path: str) -> ToolResult:
        """Get Git diff of a repository."""
        try:
            # Validate path is allowed
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            repo_path = Path(path)
            if not repo_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Repository not found"}
                )
                
            # Verify it's a git repository
            if not (repo_path / ".git").exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_GIT_REPO", "message": "Path is not a Git repository"}
                )
                
            result = subprocess.run(
                ["git", "diff"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return ToolResult(
                success=True,
                data={"diff": result.stdout}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error={"code": "TIMEOUT", "message": "Git command timed out"}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def git_log(self, path: str, limit: int = 10) -> ToolResult:
        """Get Git log of a repository."""
        try:
            # Validate path is allowed
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            repo_path = Path(path)
            if not repo_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Repository not found"}
                )
                
            # Verify it's a git repository
            if not (repo_path / ".git").exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_GIT_REPO", "message": "Path is not a Git repository"}
                )
                
            result = subprocess.run(
                ["git", "log", f"--max-count={limit}", "--pretty=format:%h %an %s"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return ToolResult(
                success=True,
                data={"log": result.stdout}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error={"code": "TIMEOUT", "message": "Git command timed out"}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def git_branches(self, path: str) -> ToolResult:
        """Get Git branches of a repository."""
        try:
            # Validate path is allowed
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            repo_path = Path(path)
            if not repo_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Repository not found"}
                )
                
            # Verify it's a git repository
            if not (repo_path / ".git").exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_GIT_REPO", "message": "Path is not a Git repository"}
                )
                
            result = subprocess.run(
                ["git", "branch", "-a"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return ToolResult(
                success=True,
                data={"branches": result.stdout}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error={"code": "TIMEOUT", "message": "Git command timed out"}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def git_current_branch(self, path: str) -> ToolResult:
        """Get current Git branch of a repository."""
        try:
            # Validate path is allowed
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            repo_path = Path(path)
            if not repo_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Repository not found"}
                )
                
            # Verify it's a git repository
            if not (repo_path / ".git").exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_GIT_REPO", "message": "Path is not a Git repository"}
                )
                
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return ToolResult(
                success=True,
                data={"branch": result.stdout.strip()}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error={"code": "TIMEOUT", "message": "Git command timed out"}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def git_create_branch(self, path: str, name: str) -> ToolResult:
        """Create a new Git branch."""
        try:
            # Validate path is allowed
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            if self.security_manager.config.security.read_only:
                return ToolResult(
                    success=False,
                    error={"code": "READ_ONLY", "message": "Server is in read-only mode"}
                )
                
            repo_path = Path(path)
            if not repo_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Repository not found"}
                )
                
            # Verify it's a git repository
            if not (repo_path / ".git").exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_GIT_REPO", "message": "Path is not a Git repository"}
                )
                
            result = subprocess.run(
                ["git", "branch", name],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Check for errors
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error={"code": "GIT_ERROR", "message": result.stderr.strip()}
                )
                
            return ToolResult(
                success=True,
                data={"message": f"Branch '{name}' created successfully"}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error={"code": "TIMEOUT", "message": "Git command timed out"}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def git_add(self, path: str, files: List[str]) -> ToolResult:
        """Add files to Git staging area."""
        try:
            # Validate path is allowed
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            if self.security_manager.config.security.read_only:
                return ToolResult(
                    success=False,
                    error={"code": "READ_ONLY", "message": "Server is in read-only mode"}
                )
                
            repo_path = Path(path)
            if not repo_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Repository not found"}
                )
                
            # Verify it's a git repository
            if not (repo_path / ".git").exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_GIT_REPO", "message": "Path is not a Git repository"}
                )
                
            # Build command
            cmd = ["git", "add"] + files
            result = subprocess.run(
                cmd,
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Check for errors
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error={"code": "GIT_ERROR", "message": result.stderr.strip()}
                )
                
            return ToolResult(
                success=True,
                data={"message": f"Added {len(files)} files"}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error={"code": "TIMEOUT", "message": "Git command timed out"}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def git_commit(self, path: str, message: str) -> ToolResult:
        """Commit staged files."""
        try:
            # Validate path is allowed
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            if self.security_manager.config.security.read_only:
                return ToolResult(
                    success=False,
                    error={"code": "READ_ONLY", "message": "Server is in read-only mode"}
                )
                
            repo_path = Path(path)
            if not repo_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Repository not found"}
                )
                
            # Verify it's a git repository
            if not (repo_path / ".git").exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_GIT_REPO", "message": "Path is not a Git repository"}
                )
                
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Check for errors
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error={"code": "GIT_ERROR", "message": result.stderr.strip()}
                )
                
            return ToolResult(
                success=True,
                data={"message": "Commit created successfully"}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error={"code": "TIMEOUT", "message": "Git command timed out"}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def git_pull(self, path: str) -> ToolResult:
        """Pull changes from remote origin."""
        try:
            # Validate path is allowed
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            repo_path = Path(path)
            if not repo_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Repository not found"}
                )
                
            # Verify it's a git repository
            if not (repo_path / ".git").exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_GIT_REPO", "message": "Path is not a Git repository"}
                )
                
            result = subprocess.run(
                ["git", "pull"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Check for errors
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error={"code": "GIT_ERROR", "message": result.stderr.strip()}
                )
                
            return ToolResult(
                success=True,
                data={"message": "Pull completed successfully"}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error={"code": "TIMEOUT", "message": "Git command timed out"}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def git_push(self, path: str) -> ToolResult:
        """Push changes to remote origin."""
        try:
            # Validate path is allowed
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            if self.security_manager.config.security.read_only:
                return ToolResult(
                    success=False,
                    error={"code": "READ_ONLY", "message": "Server is in read-only mode"}
                )
                
            repo_path = Path(path)
            if not repo_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Repository not found"}
                )
                
            # Verify it's a git repository
            if not (repo_path / ".git").exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_GIT_REPO", "message": "Path is not a Git repository"}
                )
                
            result = subprocess.run(
                ["git", "push"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Check for errors
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error={"code": "GIT_ERROR", "message": result.stderr.strip()}
                )
                
            return ToolResult(
                success=True,
                data={"message": "Push completed successfully"}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error={"code": "TIMEOUT", "message": "Git command timed out"}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )