from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class DocumentResponse(BaseModel):
    id: UUID
    case_id: UUID
    title: str
    document_type: str
    owner_user_id: Optional[UUID]
    current_version_id: Optional[UUID]
    classification: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class DocumentVersionResponse(BaseModel):
    id: UUID
    document_id: UUID
    version_number: int
    object_key: str
    sha256_hash: str
    file_size: int
    mime_type: str
    created_by: Optional[UUID]
    parent_version_id: Optional[UUID]
    created_at: datetime
    blockchain_status: str
    blockchain_tx_hash: Optional[str] = None
    blockchain_block_number: Optional[int] = None
    blockchain_timestamp: Optional[datetime] = None
    idempotency_key: Optional[str] = None
    opaque_verification_id: Optional[UUID] = None

    class Config:
        from_attributes = True

class DocumentDetailResponse(DocumentResponse):
    version_number: Optional[int] = None
    sha256_hash: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    blockchain_status: Optional[str] = None
    blockchain_tx_hash: Optional[str] = None
    blockchain_block_number: Optional[int] = None
    blockchain_timestamp: Optional[datetime] = None


class DocumentAccessGrantCreate(BaseModel):
    granted_to_user_id: UUID   # frontend field name
    permission: str  # VIEW or DOWNLOAD
    expires_at: Optional[datetime] = None

    @property
    def user_id(self) -> UUID:
        """Compatibility alias so existing backend code using req.user_id still works."""
        return self.granted_to_user_id


class DocumentAccessGrantResponse(BaseModel):
    id: UUID
    document_id: UUID
    version_id: UUID
    granted_to_user_id: UUID
    granted_by_user_id: UUID
    permission: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    salt: str
    blockchain_status: str
    blockchain_tx_hash: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentPassportVersionInfo(BaseModel):
    id: UUID                        # version UUID — required for grant calls
    version_number: int
    created_at: datetime
    sha256_hash: str
    blockchain_status: str
    blockchain_tx_hash: Optional[str] = None
    blockchain_block_number: Optional[int] = None
    blockchain_timestamp: Optional[datetime] = None
    opaque_verification_id: UUID
    public_verification_url: str

    class Config:
        from_attributes = True


class DocumentPassportResponse(BaseModel):
    document_id: UUID
    case_id: UUID
    case_title: str
    title: str
    document_type: str
    classification: str
    owner_user_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    
    # Latest authorized version details
    current_version_id: Optional[UUID] = None
    current_version_number: Optional[int] = None
    current_sha256_hash: Optional[str] = None
    current_blockchain_status: Optional[str] = None
    current_blockchain_tx_hash: Optional[str] = None
    current_blockchain_timestamp: Optional[datetime] = None
    
    # Allowed version history list
    versions: List[DocumentPassportVersionInfo]

    class Config:
        from_attributes = True
