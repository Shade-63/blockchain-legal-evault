from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.case import Case, CaseParticipant
from app.schemas.case import CaseCreateRequest, CaseResponse, CaseDetailResponse, CaseParticipantAddRequest, CaseParticipantResponse
from app.dependencies import get_current_user
from uuid import UUID
import logging

logger = logging.getLogger("security_audit")
router = APIRouter(prefix="/cases", tags=["Cases"])

@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(request: CaseCreateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Creates a new case. Only lawyers are authorized to create cases.
    The creator is automatically registered as a participant with the role 'lead_lawyer'.
    """
    # Enforce database role state check
    if current_user.role != "LAWYER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Lawyers are authorized to create cases."
        )

    # Check for duplicate case number
    existing_case = db.query(Case).filter(Case.case_number == request.case_number).first()
    if existing_case:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Case number already exists."
        )

    # Create Case
    new_case = Case(
        case_number=request.case_number,
        title=request.title,
        description=request.description,
        created_by=current_user.id
    )
    db.add(new_case)
    db.flush()  # Allocate ID

    # Auto-add creator as lead lawyer participant
    creator_participant = CaseParticipant(
        case_id=new_case.id,
        user_id=current_user.id,
        role="lead_lawyer"
    )
    db.add(creator_participant)
    db.commit()
    db.refresh(new_case)
    return new_case

@router.get("", response_model=list[CaseResponse])
def list_cases(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Lists all cases that the current user is a participant in.
    """
    # Query cases where current_user.id is in case_participants
    cases = db.query(Case).join(CaseParticipant).filter(CaseParticipant.user_id == current_user.id).all()
    return cases

@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case(case_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Retrieves case metadata and participant details.
    Enforces strict BOLA: returns 404 if the case does not exist or the user is not a participant.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    
    # 404 checks for BOLA - do not reveal if case exists
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found."
        )

    # Check if user is participant
    is_part = db.query(CaseParticipant).filter(
        CaseParticipant.case_id == case_id,
        CaseParticipant.user_id == current_user.id
    ).first()

    if not is_part:
        # Audit log the unauthorized BOLA access attempt internally
        logger.warning(
            f"Security Audit Failure: Unauthorized case access attempt. "
            f"User {current_user.id} ({current_user.role}) tried to access Case {case_id}."
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found."
        )

    # Build response detail manually to map participant profiles cleanly
    participants_list = []
    for p in case.participants:
        participants_list.append(CaseParticipantResponse(
            id=p.id,
            case_id=p.case_id,
            user_id=p.user_id,
            role=p.role,
            joined_at=p.joined_at,
            display_name=p.user.display_name,
            email=p.user.email
        ))

    return CaseDetailResponse(
        id=case.id,
        case_number=case.case_number,
        title=case.title,
        description=case.description,
        status=case.status,
        created_by=case.created_by,
        created_at=case.created_at,
        updated_at=case.updated_at,
        participants=participants_list
    )

@router.post("/{case_id}/participants", response_model=CaseParticipantResponse, status_code=status.HTTP_201_CREATED)
def add_participant(case_id: UUID, request: CaseParticipantAddRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Adds an authorized user as a case participant.
    Restricted to case creator / lead lawyer.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    
    # Strict BOLA check: if case doesn't exist OR current user is not participant, return 404
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found."
        )

    requester_part = db.query(CaseParticipant).filter(
        CaseParticipant.case_id == case_id,
        CaseParticipant.user_id == current_user.id
    ).first()

    if not requester_part:
        logger.warning(
            f"Security Audit Failure: Unauthorized participant add attempt. "
            f"User {current_user.id} ({current_user.role}) tried to manage Case {case_id}."
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found."
        )

    # Authorization Check: only the case creator / lead_lawyer can manage case participants
    is_lead = (case.created_by == current_user.id) or (requester_part.role == "lead_lawyer")
    if not is_lead:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the lead lawyer / case creator can manage case participants."
        )

    # Verify target user exists
    target_user = db.query(User).filter(User.id == request.user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target user does not exist."
        )

    # Verify user is not already a participant in the case
    already_participant = db.query(CaseParticipant).filter(
        CaseParticipant.case_id == case_id,
        CaseParticipant.user_id == request.user_id
    ).first()
    if already_participant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already registered as a participant in this case."
        )

    # Add CaseParticipant
    new_participant = CaseParticipant(
        case_id=case_id,
        user_id=request.user_id,
        role=request.role
    )
    db.add(new_participant)
    db.commit()
    db.refresh(new_participant)

    return CaseParticipantResponse(
        id=new_participant.id,
        case_id=new_participant.case_id,
        user_id=new_participant.user_id,
        role=new_participant.role,
        joined_at=new_participant.joined_at,
        display_name=target_user.display_name,
        email=target_user.email
    )
