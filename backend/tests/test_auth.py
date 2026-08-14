from app.models.user import User
from app.security import hash_password, verify_password, create_access_token
from unittest.mock import MagicMock
import uuid

def test_registration_success(client, mock_db):
    """
    Asserts user registration succeeds, hashes password, saves to db, and does not leak hash.
    """
    mock_db.query.return_value.filter.return_value.first.return_value = None

    payload = {
        "email": "lawyer@example.com",
        "password": "securepassword123",
        "display_name": "John Lawyer",
        "role": "LAWYER"
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "lawyer@example.com"
    assert "id" in data
    assert "password_hash" not in data  # Validate hash not returned in response

    # Verify user record added to DB has hashed password and is not plaintext
    added_user = mock_db.add.call_args[0][0]
    assert isinstance(added_user, User)
    assert added_user.email == "lawyer@example.com"
    assert added_user.password_hash != "securepassword123"
    assert verify_password("securepassword123", added_user.password_hash)

def test_duplicate_registration(client, mock_db):
    """
    Asserts duplicate email registration is rejected with 400 Bad Request.
    """
    existing_user = User(email="duplicate@example.com", password_hash="somehash")
    mock_db.query.return_value.filter.return_value.first.return_value = existing_user

    payload = {
        "email": "duplicate@example.com",
        "password": "securepassword123",
        "role": "LAWYER"
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]

def test_login_success(client, mock_db):
    """
    Asserts successful login returns a JWT.
    """
    hashed_pwd = hash_password("correctpassword")
    mock_user = User(
        id=uuid.uuid4(),
        email="user@example.com",
        password_hash=hashed_pwd,
        role="LAWYER",
        status="active"
    )
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    payload = {
        "email": "user@example.com",
        "password": "correctpassword"
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_invalid_credentials(client, mock_db):
    """
    Asserts invalid login fails with 401 and does not leak plaintext/hashes.
    """
    hashed_pwd = hash_password("correctpassword")
    mock_user = User(
        id=uuid.uuid4(),
        email="user@example.com",
        password_hash=hashed_pwd,
        role="LAWYER",
        status="active"
    )
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    payload = {
        "email": "user@example.com",
        "password": "wrongpassword"
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]

def test_protected_endpoint_without_auth(client):
    """
    Asserts protected endpoints reject request if auth token is missing.
    """
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 403
    assert "Not authenticated" in response.json()["detail"]

def test_authenticated_current_user(client, mock_db):
    """
    Asserts current user endpoints return correct profile when authenticated.
    """
    user_id = uuid.uuid4()
    mock_user = User(
        id=user_id,
        email="me@example.com",
        display_name="Me",
        role="JUDGE",
        status="active"
    )
    
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    token = create_access_token(data={"sub": str(user_id), "email": "me@example.com", "role": "JUDGE"})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@example.com"
    assert data["role"] == "JUDGE"
    assert "password_hash" not in data
