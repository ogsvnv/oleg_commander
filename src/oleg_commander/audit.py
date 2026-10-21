"""Audit logging for Oleg Commander."""
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import os

class AuditLogger:
    """Centralized audit logger for Oleg Commander."""
    
    def __init__(self, log_file: str = "audit.log"):
        self.log_file = Path(log_file)
        self._ensure_log_directory()
        
    def _ensure_log_directory(self):
        """Ensure the log directory exists."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
    def log_action(self, request_id: str, client_id: str, tool_name: str, 
                  target: str, arguments_summary: str, result: Dict[str, Any], 
                  duration_ms: int, approval_status: str):
        """Log an action with all relevant information."""
        
        # Create audit entry
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request_id,
            "client_id": client_id,
            "tool_name": tool_name,
            "target": target,
            "arguments_summary": arguments_summary,
            "result": result,
            "duration_ms": duration_ms,
            "approval_status": approval_status
        }
        
        # Write to file
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
            
    def get_logs(self, limit: int = 100) -> list:
        """Get recent logs."""
        logs = []
        try:
            with open(self.log_file, "r") as f:
                for line in f:
                    if line.strip():
                        logs.append(json.loads(line))
                        
            return logs[-limit:]  # Return last N logs
        except FileNotFoundError:
            return []
        except Exception:
            return []

# Global instance of audit logger
audit_logger = AuditLogger()