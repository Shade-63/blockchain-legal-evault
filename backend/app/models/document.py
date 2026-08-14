import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    document_type = Column(String, nullable=False)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    current_version_id = Column(UUID(as_uuid=True), ForeignKey("document_versions.id", use_alter=True, name="fk_documents_current_version_id"), nullable=True)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    classification = Column(String, default="unclassified", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    case = relationship("Case")
    owner = relationship("User")
    current_version = relationship("DocumentVersion", foreign_keys=[current_version_id], post_update=True)
    versions = relationship("DocumentVersion", back_populates="document", foreign_keys="DocumentVersion.document_id", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.id is None:
            self.id = uuid.uuid4()
        if self.classification is None:
            self.classification = "unclassified"
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.updated_at is None:
            self.updated_at = datetime.now(timezone.utc)

class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    object_key = Column(String, unique=True, nullable=False)
    sha256_hash = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    parent_version_id = Column(UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    idempotency_key = Column(String, unique=True, nullable=True)
    opaque_verification_id = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4, index=True)

    # Blockchain tracking fields
    blockchain_status = Column(String, default="pending", nullable=False)
    blockchain_tx_hash = Column(String, unique=True, nullable=True)
    blockchain_block_number = Column(Integer, nullable=True)
    blockchain_timestamp = Column(DateTime(timezone=True), nullable=True)

    document = relationship("Document", back_populates="versions", foreign_keys=[document_id])
    creator = relationship("User")
    parent_version = relationship("DocumentVersion", remote_side=[id])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.id is None:
            self.id = uuid.uuid4()
        if self.opaque_verification_id is None:
            self.opaque_verification_id = uuid.uuid4()
        if self.blockchain_status is None:
            self.blockchain_status = "pending"
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

from sqlalchemy import event, inspect

@event.listens_for(DocumentVersion, "before_update")
def prevent_version_updates(mapper, connection, target):
    state = inspect(target)
    immutable_fields = {
        "id", "document_id", "version_number", "object_key",
        "sha256_hash", "file_size", "mime_type", "created_by",
        "parent_version_id", "created_at", "idempotency_key",
        "opaque_verification_id"
    }
    for field in immutable_fields:
        attr = state.attrs.get(field)
        if attr and attr.history.has_changes():
            raise ValueError(f"DocumentVersion column '{field}' is read-only and cannot be mutated.")

@event.listens_for(DocumentVersion, "before_delete")
def prevent_version_deletes(mapper, connection, target):
    raise ValueError("DocumentVersion records are read-only and cannot be deleted.")


class DocumentAccessGrant(Base):
    __tablename__ = "document_access_grants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version_id = Column(UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    granted_to_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    granted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    permission = Column(String, nullable=False)  # VIEW, DOWNLOAD
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    
    # Blockchain permission commitment fields
    salt = Column(String, nullable=False)
    blockchain_status = Column(String, default="pending", nullable=False) # pending, confirmed, failed
    blockchain_tx_hash = Column(String, nullable=True)

    document = relationship("Document")
    version = relationship("DocumentVersion")
    granted_to = relationship("User", foreign_keys=[granted_to_user_id])
    granted_by = relationship("User", foreign_keys=[granted_by_user_id])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.id is None:
            self.id = uuid.uuid4()
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.salt is None:
            self.salt = uuid.uuid4().hex


@event.listens_for(DocumentAccessGrant, "before_update")
def prevent_grant_updates(mapper, connection, target):
    state = inspect(target)
    immutable_fields = {
        "id", "document_id", "version_id", "granted_to_user_id",
        "granted_by_user_id", "permission", "created_at", "expires_at", "salt"
    }
    for field in immutable_fields:
        attr = state.attrs.get(field)
        if attr and attr.history.has_changes():
            raise ValueError(f"DocumentAccessGrant core field '{field}' is immutable and cannot be updated.")

    revoked_attr = state.attrs.get("revoked_at")
    if revoked_attr and revoked_attr.history.has_changes():
        from sqlalchemy.orm.attributes import NO_VALUE
        old_val = state.committed_state.get("revoked_at")
        if old_val is not NO_VALUE and old_val is not None:
            raise ValueError("DocumentAccessGrant revoked_at field is permanent and cannot be modified after revocation.")


@event.listens_for(DocumentAccessGrant, "before_delete")
def prevent_grant_deletes(mapper, connection, target):
    raise ValueError("DocumentAccessGrant records are read-only and cannot be deleted.")

