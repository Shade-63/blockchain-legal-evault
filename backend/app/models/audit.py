import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    version_id = Column(UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    actor_type = Column(String, default="authenticated", nullable=False)  # "authenticated" or "PUBLIC_VERIFIER"
    event_type = Column(String, nullable=False)  # ACCESS_GRANTED, ACCESS_REVOKED, DOCUMENT_VIEWED, DOCUMENT_DOWNLOADED, ACCESS_DENIED
    event_metadata_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    actor = relationship("User")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.id is None:
            self.id = uuid.uuid4()
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

from sqlalchemy import event

@event.listens_for(AuditEvent, "before_update")
def prevent_audit_updates(mapper, connection, target):
    raise ValueError("Audit log entries are write-once and cannot be modified or deleted.")

@event.listens_for(AuditEvent, "before_delete")
def prevent_audit_deletes(mapper, connection, target):
    raise ValueError("Audit log entries are write-once and cannot be modified or deleted.")


def log_audit_event(event_type: str, actor_user_id, case_id=None, document_id=None, version_id=None, metadata=None, actor_type="authenticated"):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        event = AuditEvent(
            case_id=case_id,
            document_id=document_id,
            version_id=version_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            event_type=event_type,
            event_metadata_json=metadata
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

