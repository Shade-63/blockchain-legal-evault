import pytest
import uuid
import hashlib
from unittest.mock import MagicMock, patch
from app.models.user import User
from app.models.case import Case, CaseParticipant
from app.models.document import Document, DocumentVersion, DocumentAccessGrant
from app.security import create_access_token
from app.services.kms import KMSService
from app.services.crypto import encrypt_bytes, decrypt_bytes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Plaintext and dummy PDF magic bytes helpers
PDF_MAGIC = b"%PDF-1.4\nthis is a valid pdf test file content"
NOT_PDF = b"this is not a pdf file, it does not start with magic bytes"

def get_auth_headers(user_id: uuid.UUID, email: str, role: str):
    token = create_access_token(data={"sub": str(user_id), "email": email, "role": role})
    return {"Authorization": f"Bearer {token}"}

# UUID Bytes16 Encoding Check
def test_uuid_bytes16_round_trip():
    """
    Verifies that Python UUID to raw 16-bytes and back is deterministic and symmetric.
    """
    original = uuid.uuid4()
    raw_bytes = original.bytes
    assert len(raw_bytes) == 16
    reconstructed = uuid.UUID(bytes=raw_bytes)
    assert original == reconstructed

# Cryptographic Unit Tests
def test_per_version_key_derivation():
    """
    Asserts that deriving a key for different version IDs on the same document produces different keys.
    """
    doc_id = str(uuid.uuid4())
    ver_id_1 = str(uuid.uuid4())
    ver_id_2 = str(uuid.uuid4())

    key_1 = KMSService.derive_version_key(doc_id, ver_id_1)
    key_2 = KMSService.derive_version_key(doc_id, ver_id_2)

    assert key_1 != key_2
    assert len(key_1) == 32
    assert len(key_2) == 32

def test_encryption_decryption_round_trip():
    """
    Tests AES-256-GCM encryption and decryption helpers work symmetrically.
    """
    key = AESGCM.generate_key(bit_length=256)
    plaintext = b"sensitive legal document content"

    encrypted_payload = encrypt_bytes(plaintext, key)
    assert encrypted_payload != plaintext
    assert len(encrypted_payload) > len(plaintext)

    decrypted = decrypt_bytes(encrypted_payload, key)
    assert decrypted == plaintext

def test_wrong_key_decryption_failure():
    """
    Asserts decrypting an AES-256-GCM payload with an incorrect key throws a cryptographic error.
    """
    key_correct = AESGCM.generate_key(bit_length=256)
    key_incorrect = AESGCM.generate_key(bit_length=256)
    plaintext = b"confidential pleadings"

    encrypted_payload = encrypt_bytes(plaintext, key_correct)

    with pytest.raises(Exception):
        decrypt_bytes(encrypted_payload, key_incorrect)

# API router mocked validation tests
@patch("app.routers.documents.BlockchainAdapter")
@patch("app.routers.documents.StorageService")
def test_valid_pdf_upload(mock_storage_cls, mock_blockchain_cls, client, mock_db):
    """
    Asserts uploading a valid PDF with correct magic bytes, size, and header returns 201.
    """
    mock_storage = MagicMock()
    mock_storage.put_object.return_value = "etag-12345"
    mock_storage_cls.return_value = mock_storage

    mock_blockchain = MagicMock()
    mock_blockchain.register_version.return_value = "0xtxhash12345"
    mock_blockchain_cls.return_value = mock_blockchain

    user_id = uuid.uuid4()
    case_id = uuid.uuid4()

    mock_lawyer = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_part = CaseParticipant(id=uuid.uuid4(), case_id=case_id, user_id=user_id, role="lead_lawyer")

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer,
        mock_part,
        None
    ]

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    headers["X-Idempotency-Key"] = str(uuid.uuid4())

    files = {"file": ("document.pdf", PDF_MAGIC, "application/pdf")}
    data = {"title": "Plea Bargain Agreement", "document_type": "agreement"}

    response = client.post(f"/api/v1/cases/{case_id}/documents", files=files, data=data, headers=headers)
    assert response.status_code == 201
    assert response.json()["title"] == "Plea Bargain Agreement"
    assert mock_storage.put_object.called
    assert mock_blockchain.register_version.called

@patch("app.routers.documents.StorageService")
def test_invalid_magic_bytes_rejected(mock_storage_cls, client, mock_db):
    """
    Asserts files claiming to be PDF but containing wrong magic bytes are rejected.
    """
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()

    mock_lawyer = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_part = CaseParticipant(id=uuid.uuid4(), case_id=case_id, user_id=user_id, role="lead_lawyer")

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer,
        mock_part,
        None
    ]

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    headers["X-Idempotency-Key"] = str(uuid.uuid4())

    files = {"file": ("malicious.pdf", NOT_PDF, "application/pdf")}
    data = {"title": "Faked File", "document_type": "pleading"}

    response = client.post(f"/api/v1/cases/{case_id}/documents", files=files, data=data, headers=headers)
    assert response.status_code == 400
    assert "magic bytes" in response.json()["detail"]

@patch("app.routers.documents.StorageService")
def test_mismatched_extension_rejected(mock_storage_cls, client, mock_db):
    """
    Asserts uploads claiming to be application/pdf but having non-pdf extensions are rejected.
    """
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()

    mock_lawyer = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_part = CaseParticipant(id=uuid.uuid4(), case_id=case_id, user_id=user_id, role="lead_lawyer")

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer,
        mock_part,
        None
    ]

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    headers["X-Idempotency-Key"] = str(uuid.uuid4())

    files = {"file": ("spoof.txt", PDF_MAGIC, "application/pdf")}
    data = {"title": "Spoofed File", "document_type": "evidence"}

    response = client.post(f"/api/v1/cases/{case_id}/documents", files=files, data=data, headers=headers)
    assert response.status_code == 400
    assert "PDF files are supported" in response.json()["detail"]

@patch("app.routers.documents.StorageService")
def test_oversized_file_rejected(mock_storage_cls, client, mock_db):
    """
    Asserts uploads larger than 10MB are rejected.
    """
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()

    mock_lawyer = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_part = CaseParticipant(id=uuid.uuid4(), case_id=case_id, user_id=user_id, role="lead_lawyer")

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer,
        mock_part,
        None
    ]

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    headers["X-Idempotency-Key"] = str(uuid.uuid4())

    oversized_content = b"%PDF-" + b"0" * (10 * 1024 * 1024 + 10)
    files = {"file": ("big.pdf", oversized_content, "application/pdf")}
    data = {"title": "Huge Document", "document_type": "evidence"}

    response = client.post(f"/api/v1/cases/{case_id}/documents", files=files, data=data, headers=headers)
    assert response.status_code == 400
    assert "exceeds the 10MB limit" in response.json()["detail"]

@patch("app.routers.documents.StorageService")
def test_idempotency_retry_handling(mock_storage_cls, client, mock_db):
    """
    Verify upload idempotency checks.
    """
    mock_storage = MagicMock()
    mock_storage.put_object.return_value = "etag-123"
    mock_storage_cls.return_value = mock_storage

    user_id_1 = uuid.uuid4()
    user_id_2 = uuid.uuid4()
    case_id_1 = uuid.uuid4()
    case_id_2 = uuid.uuid4()

    mock_lawyer_1 = User(id=user_id_1, email="lawyer1@example.com", role="LAWYER", status="active")
    mock_lawyer_2 = User(id=user_id_2, email="lawyer2@example.com", role="LAWYER", status="active")

    mock_part_1 = CaseParticipant(id=uuid.uuid4(), case_id=case_id_1, user_id=user_id_1, role="lead_lawyer")
    mock_part_2 = CaseParticipant(id=uuid.uuid4(), case_id=case_id_2, user_id=user_id_2, role="lead_lawyer")

    idem_key = "test-idem-key-999"

    mock_existing_doc = Document(
        id=uuid.uuid4(),
        case_id=case_id_1,
        title="Existing Document",
        document_type="pleading",
        owner_user_id=user_id_1,
        idempotency_key=idem_key
    )

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer_1,
        mock_part_1,
        mock_existing_doc
    ]

    headers_1 = get_auth_headers(user_id_1, "lawyer1@example.com", "LAWYER")
    headers_1["X-Idempotency-Key"] = idem_key

    files = {"file": ("document.pdf", PDF_MAGIC, "application/pdf")}
    data = {"title": "Existing Document", "document_type": "pleading"}

    response = client.post(f"/api/v1/cases/{case_id_1}/documents", files=files, data=data, headers=headers_1)
    assert response.status_code == 200
    assert response.json()["title"] == "Existing Document"

    # Scen B: Same key + different user/case
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer_2,
        mock_part_2,
        mock_existing_doc
    ]

    headers_2 = get_auth_headers(user_id_2, "lawyer2@example.com", "LAWYER")
    headers_2["X-Idempotency-Key"] = idem_key

    response = client.post(f"/api/v1/cases/{case_id_2}/documents", files=files, data=data, headers=headers_2)
    assert response.status_code == 409

@patch("app.routers.documents.StorageService")
def test_db_failure_triggers_compensating_delete(mock_storage_cls, client, mock_db):
    """
    Asserts that if MinIO succeeds but the DB transaction fails, compensating storage delete is triggered.
    """
    mock_storage = MagicMock()
    mock_storage.put_object.return_value = "etag-ok"
    mock_storage_cls.return_value = mock_storage

    user_id = uuid.uuid4()
    case_id = uuid.uuid4()

    mock_lawyer = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_part = CaseParticipant(id=uuid.uuid4(), case_id=case_id, user_id=user_id, role="lead_lawyer")

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer,
        mock_part,
        None
    ]

    mock_db.commit.side_effect = Exception("DB Disk Write Failure")

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    headers["X-Idempotency-Key"] = str(uuid.uuid4())

    files = {"file": ("document.pdf", PDF_MAGIC, "application/pdf")}
    data = {"title": "Compensate test", "document_type": "pleading"}

    response = client.post(f"/api/v1/cases/{case_id}/documents", files=files, data=data, headers=headers)
    assert response.status_code == 500
    assert mock_storage.delete_object.called

@patch("app.routers.documents.StorageService")
def test_unauthorized_document_download_bola(mock_storage_cls, client, mock_db):
    """
    Asserts non-case participants are blocked from downloading documents (BOLA/IDOR protection returning 404).
    """
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    mock_unauth_user = User(id=user_id, email="outsider@example.com", role="CLIENT", status="active")
    mock_doc = Document(
        id=doc_id,
        case_id=case_id,
        title="Protected evidence",
        document_type="evidence",
        owner_user_id=uuid.uuid4(),
        current_version_id=uuid.uuid4()
    )

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_unauth_user,
        mock_doc,
        None
    ]

    headers = get_auth_headers(user_id, "outsider@example.com", "CLIENT")
    response = client.get(f"/api/v1/documents/{doc_id}/download", headers=headers)
    
    assert response.status_code == 404

# Verification API Unit Tests
@patch("app.routers.verify.BlockchainAdapter")
def test_verify_success(mock_blockchain_cls, client, mock_db):
    """
    Verify upload bytes + correct version context returns VERIFIED.
    """
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    sha256_hash = hashlib.sha256(PDF_MAGIC).hexdigest()

    mock_user = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    mock_blockchain = MagicMock()
    mock_blockchain.get_registration.return_value = {
        "document_id": doc_id.bytes,
        "version_id": ver_id.bytes,
        "sha256_hash": sha256_hash,
        "block_number": 4200,
        "timestamp": 1782345000,
        "registered_by": "0xaddress",
        "is_registered": True
    }
    mock_blockchain_cls.return_value = mock_blockchain

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    files = {"file": ("document.pdf", PDF_MAGIC, "application/pdf")}
    data = {"document_id": str(doc_id), "version_id": str(ver_id)}

    response = client.post("/api/v1/verify", files=files, data=data, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "VERIFIED"

@patch("app.routers.verify.BlockchainAdapter")
def test_verify_tamper_integrity_failure(mock_blockchain_cls, client, mock_db):
    """
    Verify a one-byte difference in the document returns INTEGRITY_FAILURE.
    """
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    # Hash matches the original PDF_MAGIC, but we upload modified bytes (NOT_PDF)
    sha256_hash = hashlib.sha256(PDF_MAGIC).hexdigest()

    mock_user = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    mock_blockchain = MagicMock()
    mock_blockchain.get_registration.return_value = {
        "document_id": doc_id.bytes,
        "version_id": ver_id.bytes,
        "sha256_hash": sha256_hash,
        "block_number": 4200,
        "timestamp": 1782345000,
        "registered_by": "0xaddress",
        "is_registered": True
    }
    mock_blockchain_cls.return_value = mock_blockchain

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    files = {"file": ("document.pdf", NOT_PDF, "application/pdf")} # Changed content
    data = {"document_id": str(doc_id), "version_id": str(ver_id)}

    response = client.post("/api/v1/verify", files=files, data=data, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "INTEGRITY_FAILURE"

@patch("app.routers.verify.BlockchainAdapter")
def test_verify_unregistered_returns_not_found(mock_blockchain_cls, client, mock_db):
    """
    Verify an unknown version ID returns RECORD_NOT_FOUND.
    """
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()

    mock_user = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    mock_blockchain = MagicMock()
    mock_blockchain.get_registration.return_value = None  # Not registered
    mock_blockchain_cls.return_value = mock_blockchain

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    files = {"file": ("document.pdf", PDF_MAGIC, "application/pdf")}
    data = {"document_id": str(doc_id), "version_id": str(ver_id)}

    response = client.post("/api/v1/verify", files=files, data=data, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "RECORD_NOT_FOUND"

@patch("app.routers.verify.BlockchainAdapter")
def test_verify_rpc_offline_unavailable(mock_blockchain_cls, client, mock_db):
    """
    Verify RPC failure throws VERIFICATION_UNAVAILABLE.
    """
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()

    mock_user = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    mock_blockchain = MagicMock()
    mock_blockchain.get_registration.side_effect = Exception("RPC node connection refused")
    mock_blockchain_cls.return_value = mock_blockchain

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    files = {"file": ("document.pdf", PDF_MAGIC, "application/pdf")}
    data = {"document_id": str(doc_id), "version_id": str(ver_id)}

    response = client.post("/api/v1/verify", files=files, data=data, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "VERIFICATION_UNAVAILABLE"

# M4 Versioning & Immutability Unit Tests
from app.models.document import prevent_version_updates, prevent_version_deletes

@patch("app.routers.documents.BlockchainAdapter")
@patch("app.routers.documents.StorageService")
def test_sequential_version_creation(mock_storage_cls, mock_blockchain_cls, client, mock_db):
    """
    Asserts uploading a new version increments version_number and links parent_version_id correctly.
    """
    mock_storage = MagicMock()
    mock_storage.put_object.return_value = "etag-ok"
    mock_storage_cls.return_value = mock_storage

    mock_blockchain = MagicMock()
    mock_blockchain.register_version.return_value = "0xtxhash-version2"
    mock_blockchain_cls.return_value = mock_blockchain

    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    v1_id = uuid.uuid4()
    case_id = uuid.uuid4()

    mock_lawyer = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_part = CaseParticipant(id=uuid.uuid4(), case_id=case_id, user_id=user_id, role="lead_lawyer")
    
    # Document with existing V1 version
    mock_doc = Document(
        id=doc_id,
        case_id=case_id,
        title="Agreement",
        document_type="agreement",
        owner_user_id=user_id,
        current_version_id=v1_id
    )

    mock_latest_ver = DocumentVersion(
        id=v1_id,
        document_id=doc_id,
        version_number=1,
        object_key=f"documents/{doc_id}/{v1_id}",
        sha256_hash="hash1",
        file_size=100,
        mime_type="application/pdf",
        created_by=user_id
    )

    # Database mock responses - dynamic dispatch by model class type
    def dynamic_query(model):
        q = MagicMock()
        if model == User:
            q.filter.return_value.first.return_value = mock_lawyer
        elif model == Document:
            q.filter.return_value.first.return_value = mock_doc
            q.filter.return_value.with_for_update.return_value.first.return_value = mock_doc
        elif model == CaseParticipant:
            q.filter.return_value.first.return_value = mock_part
        elif model == DocumentVersion:
            q.filter.return_value.first.return_value = None  # no idempotency conflict
            q.filter.return_value.order_by.return_value.first.return_value = mock_latest_ver
        return q

    mock_db.query.side_effect = dynamic_query

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    headers["X-Idempotency-Key"] = str(uuid.uuid4())

    files = {"file": ("document_v2.pdf", PDF_MAGIC, "application/pdf")}
    response = client.post(f"/api/v1/documents/{doc_id}/versions", files=files, headers=headers)
    
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["version_number"] == 2
    assert res_data["parent_version_id"] == str(v1_id)
    assert mock_storage.put_object.called
    assert mock_blockchain.register_version.called

def test_prevent_orm_version_mutation():
    """
    Asserts that changing an attribute on DocumentVersion model is blocked by ORM listener.
    """
    ver = DocumentVersion(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        version_number=1,
        object_key="some-key",
        sha256_hash="hash",
        file_size=100,
        mime_type="application/pdf"
    )
    
    from sqlalchemy.orm import Mapper
    # Manually invoke mapper event to test listener
    with pytest.raises(ValueError, match="is read-only and cannot be mutated"):
        prevent_version_updates(None, None, ver)

def test_prevent_orm_version_deletion():
    """
    Asserts that deleting a DocumentVersion model is blocked by ORM listener.
    """
    ver = DocumentVersion(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        version_number=1,
        object_key="some-key",
        sha256_hash="hash",
        file_size=100,
        mime_type="application/pdf"
    )
    
    with pytest.raises(ValueError, match="DocumentVersion records are read-only and cannot be deleted."):
        prevent_version_deletes(None, None, ver)

@patch("app.routers.documents.StorageService")
def test_version_upload_idempotency_success(mock_storage_cls, client, mock_db):
    """
    Asserts that resubmitting a version creation request with the same user, doc, and idempotency key returns 200.
    """
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    case_id = uuid.uuid4()
    idem_key = "version-idem-key-888"

    mock_lawyer = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_part = CaseParticipant(id=uuid.uuid4(), case_id=case_id, user_id=user_id, role="lead_lawyer")
    
    mock_doc = Document(
        id=doc_id,
        case_id=case_id,
        title="Agreement",
        document_type="agreement",
        owner_user_id=user_id,
        current_version_id=ver_id
    )

    mock_existing_ver = DocumentVersion(
        id=ver_id,
        document_id=doc_id,
        version_number=2,
        object_key="key",
        sha256_hash="hash",
        file_size=100,
        mime_type="application/pdf",
        created_by=user_id,
        idempotency_key=idem_key
    )

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer,       # current user (dependencies evaluation)
        mock_doc,          # fetch doc
        mock_part,         # verify participant
        mock_existing_ver  # idempotency lookup success
    ]

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    headers["X-Idempotency-Key"] = idem_key

    files = {"file": ("document_v2.pdf", PDF_MAGIC, "application/pdf")}
    response = client.post(f"/api/v1/documents/{doc_id}/versions", files=files, headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(ver_id)

@patch("app.routers.documents.StorageService")
def test_version_upload_idempotency_conflict(mock_storage_cls, client, mock_db):
    """
    Asserts that using the same idempotency key for a different user/document returns 409.
    """
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    case_id = uuid.uuid4()
    idem_key = "version-idem-key-888"

    mock_lawyer = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_part = CaseParticipant(id=uuid.uuid4(), case_id=case_id, user_id=user_id, role="lead_lawyer")
    
    mock_doc = Document(
        id=doc_id,
        case_id=case_id,
        title="Agreement",
        document_type="agreement",
        owner_user_id=user_id
    )

    # Mock version created by a different user
    mock_existing_ver = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc_id,
        version_number=2,
        object_key="key",
        sha256_hash="hash",
        file_size=100,
        mime_type="application/pdf",
        created_by=uuid.uuid4(),  # Different creator
        idempotency_key=idem_key
    )

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer,       # current user (dependencies evaluation)
        mock_doc,          # fetch doc
        mock_part,         # verify participant
        mock_existing_ver  # idempotency lookup returns existing
    ]

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    headers["X-Idempotency-Key"] = idem_key

    files = {"file": ("document_v2.pdf", PDF_MAGIC, "application/pdf")}
    response = client.post(f"/api/v1/documents/{doc_id}/versions", files=files, headers=headers)
    assert response.status_code == 409


def test_get_case_documents_authorized_lead_lawyer(client, mock_db):
    """
    Asserts that an authorized case participant (Lead Lawyer) can list case documents.
    """
    from datetime import datetime
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()

    mock_lawyer = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_part = CaseParticipant(id=uuid.uuid4(), case_id=case_id, user_id=user_id, role="lead_lawyer")
    mock_case = Case(id=case_id, case_number="CASE-2026-001", title="Title", created_by=user_id)
    mock_doc = Document(
        id=uuid.uuid4(),
        case_id=case_id,
        title="Test Doc",
        document_type="Pleading",
        classification="public",
        owner_user_id=user_id,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer,  # get_current_user
        mock_part,    # verify_case_participant
        mock_case     # is_lead_lawyer
    ]
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_doc]

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    response = client.get(f"/api/v1/cases/{case_id}/documents", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Test Doc"


def test_get_case_documents_unauthorized(client, mock_db):
    """
    Asserts that a non-participant receives 404 when enumerating documents.
    """
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()

    mock_stranger = User(id=user_id, email="stranger@example.com", role="CLIENT", status="active")

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_stranger,  # get_current_user
        None           # verify_case_participant (not a participant -> None)
    ]

    headers = get_auth_headers(user_id, "stranger@example.com", "CLIENT")
    response = client.get(f"/api/v1/cases/{case_id}/documents", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Case not found."


def test_get_case_documents_empty(client, mock_db):
    """
    Asserts that an empty case returns an empty list [].
    """
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()

    mock_lawyer = User(id=user_id, email="lawyer@example.com", role="LAWYER", status="active")
    mock_part = CaseParticipant(id=uuid.uuid4(), case_id=case_id, user_id=user_id, role="lead_lawyer")
    mock_case = Case(id=case_id, case_number="CASE-2026-001", title="Title", created_by=user_id)

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_lawyer,  # get_current_user
        mock_part,    # verify_case_participant
        mock_case     # is_lead_lawyer
    ]
    mock_db.query.return_value.filter.return_value.all.return_value = []

    headers = get_auth_headers(user_id, "lawyer@example.com", "LAWYER")
    response = client.get(f"/api/v1/cases/{case_id}/documents", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_get_case_documents_client_with_grant(client, mock_db):
    """
    Asserts that a standard participant (Client) can see a document in the case list
    if and only if they have an active version grant.
    """
    from datetime import datetime
    user_id = uuid.uuid4()
    lawyer_id = uuid.uuid4()
    case_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()

    mock_client = User(id=user_id, email="client@example.com", role="CLIENT", status="active")
    mock_part = CaseParticipant(id=uuid.uuid4(), case_id=case_id, user_id=user_id, role="client")
    mock_case = Case(id=case_id, case_number="CASE-2026-001", title="Title", created_by=lawyer_id)
    
    mock_doc = Document(
        id=doc_id,
        case_id=case_id,
        title="Shared Doc",
        document_type="Evidence",
        classification="restricted",
        owner_user_id=lawyer_id,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    mock_grant = DocumentAccessGrant(
        id=uuid.uuid4(),
        document_id=doc_id,
        version_id=ver_id,
        granted_to_user_id=user_id,
        granted_by_user_id=lawyer_id,
        permission="VIEW",
        blockchain_status="confirmed",
        salt="salt"
    )

    # 1. get_current_user: mock_client
    # 2. verify_case_participant: mock_part
    # 3. is_lead_lawyer: case lookup (creator is lawyer_id != user_id -> proceeds to CP lookup)
    # 4. is_lead_lawyer: explicit lead_lawyer participant query (returns None -> not lead lawyer)
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_client,  # get_current_user
        mock_part,    # verify_case_participant
        mock_case,    # is_lead_lawyer (case creator check)
        None          # is_lead_lawyer (explicit role check)
    ]
    
    # .all() is called:
    #   - First for docs list: returns [mock_doc]
    #   - Second for active grants (inside get_active_grants_for_document): returns [mock_grant]
    mock_db.query.return_value.filter.return_value.all.side_effect = [
        [mock_doc],
        [mock_grant]
    ]

    headers = get_auth_headers(user_id, "client@example.com", "CLIENT")
    response = client.get(f"/api/v1/cases/{case_id}/documents", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Shared Doc"


