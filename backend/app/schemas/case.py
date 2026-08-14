from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class CaseCreateRequest(BaseModel):
    case_number: str
    title: str
    description: Optional[str] = None

class CaseParticipantAddRequest(BaseModel):
    user_id: UUID
    role: str

class CaseParticipantResponse(BaseModel):
    id: UUID
    case_id: UUID
    user_id: UUID
    role: str
    joined_at: datetime
    display_name: Optional[str] = None
    email: str

    class Config:
        from_attributes = True

class CaseResponse(BaseModel):
    id: UUID
    case_number: str
    title: str
    description: Optional[str]
    status: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CaseDetailResponse(CaseResponse):
    participants: List[CaseParticipantResponse]
