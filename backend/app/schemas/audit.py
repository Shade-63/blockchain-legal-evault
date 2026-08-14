from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class AuditEventResponse(BaseModel):
    id: UUID
    case_id: Optional[UUID] = None
    document_id: Optional[UUID] = None
    version_id: Optional[UUID] = None
    actor_user_id: UUID
    event_type: str
    event_metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True
