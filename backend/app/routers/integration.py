from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.case import Case, CaseParticipant
from app.models.audit import log_audit_event
from app.dependencies import get_current_user
from pydantic import BaseModel
from typing import Optional, List
import uuid
import logging

logger = logging.getLogger("security_audit")
router = APIRouter(prefix="/integration", tags=["Integration"])

class CaseSyncRequest(BaseModel):
    case_number: str
    title: str
    description: Optional[str] = None
    participant_ids: Optional[List[uuid.UUID]] = None

@router.post("/cases/sync", status_code=status.HTTP_201_CREATED)
def sync_external_case(
    request: CaseSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Simulates external eCourts case sync. Links/creates the case in eVault.
    """
    # Authorization: Only lawyers can sync external cases
    if current_user.role != "LAWYER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Lawyers are authorized to sync cases."
        )

    # 1. Look up case by case_number
    case = db.query(Case).filter(Case.case_number == request.case_number).first()
    created = False
    if not case:
        case = Case(
            case_number=request.case_number,
            title=request.title,
            description=request.description,
            created_by=current_user.id
        )
        db.add(case)
        db.flush()
        created = True

    # 2. Add creator as lead lawyer participant if not already
    creator_part = db.query(CaseParticipant).filter(
        CaseParticipant.case_id == case.id,
        CaseParticipant.user_id == current_user.id
    ).first()
    if not creator_part:
        creator_part = CaseParticipant(
            case_id=case.id,
            user_id=current_user.id,
            role="lead_lawyer"
        )
        db.add(creator_part)

    # 3. Add other participants
    if request.participant_ids:
        for p_id in request.participant_ids:
            # Check if user exists
            usr = db.query(User).filter(User.id == p_id).first()
            if not usr:
                continue
            # Check if participant already exists
            part = db.query(CaseParticipant).filter(
                CaseParticipant.case_id == case.id,
                CaseParticipant.user_id == p_id
            ).first()
            if not part:
                role = "lead_lawyer" if usr.role == "LAWYER" else "client"
                part = CaseParticipant(
                    case_id=case.id,
                    user_id=p_id,
                    role=role
                )
                db.add(part)

    db.commit()
    db.refresh(case)

    # Audit log the case synchronization/import
    log_audit_event(
        event_type="CASE_IMPORTED",
        actor_user_id=current_user.id,
        case_id=case.id,
        document_id=None,
        version_id=None,
        metadata={
            "case_number": case.case_number,
            "is_new": created,
            "source": "eCourts_Sync_Adapter"
        }
    )

    return {
        "status": "success",
        "case_id": str(case.id),
        "case_number": case.case_number,
        "message": "Case synchronized successfully."
    }
