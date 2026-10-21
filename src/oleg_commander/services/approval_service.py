"""Approval service for Oleg Commander."""
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass

@dataclass
class ApprovalRequest:
    """Represents an approval request."""
    
    id: str
    tool_name: str
    arguments: Dict[str, any]
    requested_by: str
    created_at: datetime
    expires_at: datetime
    approved: bool = False
    rejected: bool = False
    
    def is_expired(self) -> bool:
        """Check if the approval request has expired."""
        return datetime.now() > self.expires_at
    
    def can_be_approved(self) -> bool:
        """Check if the request can still be approved."""
        return not (self.approved or self.rejected or self.is_expired())

class ApprovalService:
    """Service for managing approval requests."""
    
    def __init__(self, timeout_minutes: int = 10):
        self.requests: Dict[str, ApprovalRequest] = {}
        self.timeout_minutes = timeout_minutes
        
    def create_request(self, tool_name: str, arguments: Dict[str, any], 
                     requested_by: str) -> ApprovalRequest:
        """Create an approval request."""
        request_id = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(minutes=self.timeout_minutes)
        
        request = ApprovalRequest(
            id=request_id,
            tool_name=tool_name,
            arguments=arguments,
            requested_by=requested_by,
            created_at=datetime.now(),
            expires_at=expires_at
        )
        
        self.requests[request_id] = request
        return request
        
    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get an approval request by ID."""
        return self.requests.get(request_id)
        
    def approve_request(self, request_id: str) -> bool:
        """Approve an approval request."""
        request = self.get_request(request_id)
        if not request or not request.can_be_approved():
            return False
            
        request.approved = True
        return True
        
    def reject_request(self, request_id: str) -> bool:
        """Reject an approval request."""
        request = self.get_request(request_id)
        if not request or not request.can_be_approved():
            return False
            
        request.rejected = True
        return True
        
    def get_pending_requests(self) -> List[ApprovalRequest]:
        """Get all pending approval requests."""
        return [req for req in self.requests.values() 
                if req.can_be_approved()]
                
    def cleanup_expired_requests(self):
        """Remove expired requests."""
        expired_ids = [rid for rid, req in self.requests.items() 
                      if req.is_expired()]
        
        for rid in expired_ids:
            del self.requests[rid]