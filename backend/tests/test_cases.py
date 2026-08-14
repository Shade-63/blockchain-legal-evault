import pytest
import uuid
from app.models.user import User
from app.models.case import Case, CaseParticipant
from app.security import create_access_token
from unittest.mock import MagicMock

def test_create_case_lawyer_success(client, mock_db):
    """
    Asserts a Lawyer can successfully create a case and is automatically registered.
    """
    user_id = uuid.uuid4()
    mock_lawyer = User(
        id=user_id,
        email="lawyer@example.com",
        role="LAWYER",
        status="active"
    )
    
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer,  # get_current_user DB lookup
        None          # case_number uniqueness query
    ]

    token = create_access_token(data={"sub": str(user_id), "email": "lawyer@example.com", "role": "LAWYER"})
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "case_number": "CASE-2026-00421",
        "title": "Sharma vs Kumar",
        "description": "Demo case"
    }
    response = client.post("/api/v1/cases", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["case_number"] == "CASE-2026-00421"
    assert data["created_by"] == str(user_id)

def test_create_case_non_lawyer_rejected(client, mock_db):
    """
    Asserts Judge, Client, or Admin roles are blocked from creating cases.
    """
    user_id = uuid.uuid4()
    mock_judge = User(
        id=user_id,
        email="judge@example.com",
        role="JUDGE",
        status="active"
    )
    mock_db.query.return_value.filter.return_value.first.return_value = mock_judge

    token = create_access_token(data={"sub": str(user_id), "email": "judge@example.com", "role": "JUDGE"})
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "case_number": "CASE-2026-00421",
        "title": "Sharma vs Kumar"
    }
    response = client.post("/api/v1/cases", json=payload, headers=headers)
    assert response.status_code == 403
    assert "Only Lawyers are authorized" in response.json()["detail"]

def test_get_case_participant_success(client, mock_db):
    """
    Asserts a registered case participant can retrieve case details.
    """
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()
    mock_lawyer = User(
        id=user_id,
        email="lawyer@example.com",
        role="LAWYER",
        status="active",
        display_name="John Lawyer"
    )
    
    mock_case = Case(
        id=case_id,
        case_number="CASE-2026-00421",
        title="Sharma vs Kumar",
        created_by=user_id
    )
    
    mock_part = CaseParticipant(
        id=uuid.uuid4(),
        case_id=case_id,
        user_id=user_id,
        role="lead_lawyer",
        joined_at=sa_time_stub()
    )
    mock_part.user = mock_lawyer
    mock_case.participants = [mock_part]
    
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer,  # get_current_user
        mock_case,    # get_case
        mock_part     # is_participant verification check
    ]

    token = create_access_token(data={"sub": str(user_id), "email": "lawyer@example.com", "role": "LAWYER"})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.get(f"/api/v1/cases/{case_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(case_id)
    assert len(data["participants"]) == 1
    assert data["participants"][0]["user_id"] == str(user_id)

def test_get_case_non_participant_returns_404(client, mock_db):
    """
    Asserts BOLA/IDOR attempt returns 404 Not Found to obscure case presence.
    """
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()
    mock_lawyer = User(
        id=user_id,
        email="lawyer@example.com",
        role="LAWYER",
        status="active"
    )
    
    mock_case = Case(
        id=case_id,
        case_number="CASE-2026-00421",
        title="Sharma vs Kumar",
        created_by=uuid.uuid4()
    )
    
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer,  # get_current_user
        mock_case,    # get_case
        None          # is_participant verification returns None (not participant)
    ]

    token = create_access_token(data={"sub": str(user_id), "email": "lawyer@example.com", "role": "LAWYER"})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.get(f"/api/v1/cases/{case_id}", headers=headers)
    assert response.status_code == 404
    assert "Case not found" in response.json()["detail"]

def test_add_participant_creator_success(client, mock_db):
    """
    Asserts the case creator/lead lawyer can add case participants.
    """
    creator_id = uuid.uuid4()
    target_id = uuid.uuid4()
    case_id = uuid.uuid4()
    
    mock_creator = User(id=creator_id, email="creator@example.com", role="LAWYER", status="active")
    mock_target = User(id=target_id, email="target@example.com", display_name="Client", role="CLIENT", status="active")
    mock_case = Case(id=case_id, created_by=creator_id, case_number="C1", title="T1")
    
    mock_part = CaseParticipant(case_id=case_id, user_id=creator_id, role="lead_lawyer")
    
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_creator,  # get_current_user
        mock_case,     # get_case
        mock_part,     # requester CaseParticipant check
        mock_target,   # target User exist check
        None           # target already participant check
    ]

    token = create_access_token(data={"sub": str(creator_id), "email": "creator@example.com", "role": "LAWYER"})
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "user_id": str(target_id),
        "role": "client"
    }
    response = client.post(f"/api/v1/cases/{case_id}/participants", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == str(target_id)
    assert data["role"] == "client"

def test_add_participant_non_lead_rejected(client, mock_db):
    """
    Asserts a lawyer participant who is NOT lead_lawyer/creator is blocked from managing participants.
    """
    creator_id = uuid.uuid4()
    lawyer_id = uuid.uuid4()
    target_id = uuid.uuid4()
    case_id = uuid.uuid4()
    
    mock_lawyer = User(id=lawyer_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_case = Case(id=case_id, created_by=creator_id, case_number="C1", title="T1")
    
    # Registered participant, but not creator and not lead_lawyer
    mock_part = CaseParticipant(case_id=case_id, user_id=lawyer_id, role="opposing_counsel")
    
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer,  # get_current_user
        mock_case,     # get_case
        mock_part      # requester CaseParticipant check
    ]

    token = create_access_token(data={"sub": str(lawyer_id), "email": "lawyer@example.com", "role": "LAWYER"})
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "user_id": str(target_id),
        "role": "client"
    }
    response = client.post(f"/api/v1/cases/{case_id}/participants", json=payload, headers=headers)
    assert response.status_code == 403
    assert "Only the lead lawyer" in response.json()["detail"]

def sa_time_stub():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
