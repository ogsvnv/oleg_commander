"""Filesystem tools for Oleg Commander."""
import asyncio
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from .base import ToolResult

class FilesystemTool:
    """Tools for working with the local filesystem."""
    
    def __init__(self, security_manager):
        self.security_manager = security_manager
    
    async def list_directory(self, path: str, depth: int = 1) -> ToolResult:
        """List files and directories in a given path."""
        try:
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            directory = Path(path)
            if not directory.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Directory not found"}
                )
            
            if not directory.is_dir():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_DIR", "message": "Path is not a directory"}
                )
                
            items = []
            for item in directory.iterdir():
                if depth > 0:
                    items.append({
                        "name": item.name,
                        "path": str(item),
                        "is_directory": item.is_dir(),
                        "size": item.stat().st_size if item.is_file() else 0
                    })
                    
            return ToolResult(
                success=True,
                data={"items": items}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
    
    async def read_file(self, path: str, offset: int = 0, limit: Optional[int] = None) -> ToolResult:
        """Read text content from a file."""
        try:
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            file_path = Path(path)
            if not file_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "File not found"}
                )
            
            if not file_path.is_file():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FILE", "message": "Path is not a file"}
                )
                
            # Read content with offset and limit
            content = file_path.read_text(encoding='utf-8')
            
            if offset > 0:
                content = content[offset:]
                
            if limit is not None:
                content = content[:limit]
                
            return ToolResult(
                success=True,
                data={"content": content}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def read_multiple_files(self, paths: List[str]) -> ToolResult:
        """Read multiple files at once."""
        try:
            results = []
            for path in paths:
                if not self.security_manager.is_path_allowed(path):
                    results.append({
                        "path": path,
                        "success": False,
                        "error": "Access to path denied"
                    })
                    continue
                    
                file_path = Path(path)
                if not file_path.exists():
                    results.append({
                        "path": path,
                        "success": False,
                        "error": "File not found"
                    })
                    continue
                    
                try:
                    content = file_path.read_text(encoding='utf-8')
                    results.append({
                        "path": path,
                        "success": True,
                        "content": content
                    })
                except Exception as e:
                    results.append({
                        "path": path,
                        "success": False,
                        "error": str(e)
                    })
                    
            return ToolResult(
                success=True,
                data={"results": results}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def write_file(self, path: str, content: str) -> ToolResult:
        """Write text content to a file."""
        try:
            if self.security_manager.is_path_allowed(path):
                # This is only allowed in read-write mode
                if not self.security_manager.can_modify():
                    return ToolResult(
                        success=False,
                        error={"code": "READ_ONLY", "message": "Server is in read-only mode"}
                    )
                
                file_path = Path(path)
                parent_dir = file_path.parent
                
                # Create directories if needed
                if not parent_dir.exists():
                    parent_dir.mkdir(parents=True, exist_ok=True)
                    
                file_path.write_text(content, encoding='utf-8')
                
                return ToolResult(success=True, data={"message": "File written successfully"})
            else:
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def edit_file(self, path: str, old_text: str, new_text: str) -> ToolResult:
        """Perform a find-and-replace operation in a file."""
        try:
            if self.security_manager.is_path_allowed(path):
                # This is only allowed in read-write mode
                if not self.security_manager.can_modify():
                    return ToolResult(
                        success=False,
                        error={"code": "READ_ONLY", "message": "Server is in read-only mode"}
                    )
                
                file_path = Path(path)
                if not file_path.exists():
                    return ToolResult(
                        success=False,
                        error={"code": "NOT_FOUND", "message": "File not found"}
                    )
                
                content = file_path.read_text(encoding='utf-8')
                
                # Find and replace
                replaced_content = content.replace(old_text, new_text)
                if content == replaced_content:
                    return ToolResult(
                        success=False,
                        error={"code": "NOT_FOUND", "message": "Text to be replaced was not found"}
                    )
                    
                # Write back to file (atomic write)
                file_path.write_text(replaced_content, encoding='utf-8')
                
                return ToolResult(success=True, data={"message": "File edited successfully"})
            else:
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def search_files(self, path: str, pattern: str) -> ToolResult:
        """Search files by name pattern."""
        try:
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            search_dir = Path(path)
            if not search_dir.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Directory not found"}
                )
            
            if not search_dir.is_dir():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_DIR", "message": "Path is not a directory"}
                )
                
            matched_files = []
            for item in search_dir.rglob(pattern):
                if item.is_file():
                    matched_files.append({
                        "path": str(item),
                        "name": item.name
                    })
                    
            return ToolResult(
                success=True,
                data={"files": matched_files}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def search_content(self, path: str, query: str) -> ToolResult:
        """Search for text content in files."""
        try:
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            search_dir = Path(path)
            if not search_dir.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Directory not found"}
                )
            
            matched_files = []
            for item in search_dir.rglob("*"):
                if not item.is_file() or item.name.startswith('.'):
                    continue
                    
                try:
                    content = item.read_text(encoding='utf-8')
                    if query in content:
                        matched_files.append({
                            "path": str(item),
                            "match_count": content.count(query)
                        })
                except (UnicodeDecodeError, PermissionError):
                    # Skip files that can't be read
                    continue
                    
            return ToolResult(
                success=True,
                data={"files": matched_files}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def get_file_info(self, path: str) -> ToolResult:
        """Get information about a file."""
        try:
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            file_path = Path(path)
            if not file_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "File not found"}
                )
            
            stat = file_path.stat()
            
            info = {
                "path": str(file_path),
                "size": stat.st_size,
                "is_directory": file_path.is_dir(),
                "is_file": file_path.is_file(),
                "created_time": stat.st_ctime,
                "modified_time": stat.st_mtime,
                "permissions": oct(stat.st_mode)[-3:]
            }
            
            return ToolResult(
                success=True,
                data={"info": info}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def create_directory(self, path: str) -> ToolResult:
        """Create a directory."""
        try:
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            if not self.security_manager.can_modify():
                return ToolResult(
                    success=False,
                    error={"code": "READ_ONLY", "message": "Server is in read-only mode"}
                )
                
            dir_path = Path(path)
            # Create all parent directories
            dir_path.mkdir(parents=True, exist_ok=True)
            
            return ToolResult(success=True, data={"message": "Directory created successfully"})
            
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def move_file(self, source: str, destination: str) -> ToolResult:
        """Move a file."""
        try:
            if not self.security_manager.is_path_allowed(source):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to source path denied"}
                )
                
            if not self.security_manager.is_path_allowed(destination):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to destination path denied"}
                )
                
            if not self.security_manager.can_modify():
                return ToolResult(
                    success=False,
                    error={"code": "READ_ONLY", "message": "Server is in read-only mode"}
                )
                
            source_path = Path(source)
            dest_path = Path(destination)
            
            if not source_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Source file not found"}
                )
            
            # Create parent directory for destination
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Move the file
            source_path.rename(dest_path)
            
            return ToolResult(success=True, data={"message": "File moved successfully"})
            
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def copy_file(self, source: str, destination: str) -> ToolResult:
        """Copy a file."""
        try:
            if not self.security_manager.is_path_allowed(source):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to source path denied"}
                )
                
            if not self.security_manager.is_path_allowed(destination):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to destination path denied"}
                )
                
            if not self.security_manager.can_modify():
                return ToolResult(
                    success=False,
                    error={"code": "READ_ONLY", "message": "Server is in read-only mode"}
                )
                
            source_path = Path(source)
            dest_path = Path(destination)
            
            if not source_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "Source file not found"}
                )
                
            # Create parent directory for destination
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy the file
            import shutil
            shutil.copy2(source_path, dest_path)
            
            return ToolResult(success=True, data={"message": "File copied successfully"})
            
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )
            
    async def delete_file(self, path: str) -> ToolResult:
        """Delete a file."""
        try:
            if not self.security_manager.is_path_allowed(path):
                return ToolResult(
                    success=False,
                    error={"code": "FORBIDDEN", "message": "Access to path denied"}
                )
                
            if not self.security_manager.can_modify():
                return ToolResult(
                    success=False,
                    error={"code": "READ_ONLY", "message": "Server is in read-only mode"}
                )
                
            file_path = Path(path)
            
            if not file_path.exists():
                return ToolResult(
                    success=False,
                    error={"code": "NOT_FOUND", "message": "File not found"}
                )
                
            # Delete the file
            file_path.unlink()
            
            return ToolResult(success=True, data={"message": "File deleted successfully"})
            
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "UNKNOWN_ERROR", "message": str(e)}
            )

