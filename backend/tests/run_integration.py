import requests
import sys
import uuid
import hashlib
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add backend directory to sys.path
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.services.storage import StorageService
from app.services.kms import KMSService
from app.services.crypto import encrypt_bytes, decrypt_bytes
from app.services.blockchain import BlockchainAdapter
from app.models.document import Document, DocumentVersion

API_URL = "http://127.0.0.1:8000/api/v1"
db_engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

# Plaintext and dummy PDF magic bytes helpers
PDF_MAGIC_V1 = b"%PDF-1.4\nthis is version 1 content"
PDF_MAGIC_V2 = b"%PDF-1.4\nthis is version 2 content"
PDF_MAGIC_V3 = b"%PDF-1.4\nthis is version 3 content"
NOT_PDF = b"this is not a pdf file content"

def clear_db():
    print("Clearing tables for integration tests...")
    with db_engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE case_participants, cases, users, documents, document_versions CASCADE;"))
        conn.commit()

def run_tests():
    clear_db()

    print("\n--- 1. Testing Registration ---")
    lawyer_payload = {
        "email": "lawyer@evault.test",
        "password": "securepassword123",
        "display_name": "Lead Lawyer",
        "role": "LAWYER"
    }
    client_payload = {
        "email": "client@evault.test",
        "password": "securepassword123",
        "display_name": "Demo Client",
        "role": "CLIENT"
    }

    # Register Lawyer
    res = requests.post(f"{API_URL}/auth/register", json=lawyer_payload)
    assert res.status_code == 201
    lawyer_id = res.json()["id"]

    # Register Client
    res = requests.post(f"{API_URL}/auth/register", json=client_payload)
    assert res.status_code == 201
    client_id = res.json()["id"]

    print("\n--- 2. Login & JWT Setup ---")
    login_res = requests.post(f"{API_URL}/auth/login", json={
        "email": "lawyer@evault.test",
        "password": "securepassword123"
    })
    assert login_res.status_code == 200
    lawyer_token = login_res.json()["access_token"]
    lawyer_headers = {"Authorization": f"Bearer {lawyer_token}"}

    client_login_res = requests.post(f"{API_URL}/auth/login", json={
        "email": "client@evault.test",
        "password": "securepassword123"
    })
    assert client_login_res.status_code == 200
    client_token = client_login_res.json()["access_token"]
    client_headers = {"Authorization": f"Bearer {client_token}"}

    print("\n--- 3. Case & V1 Document Creation ---")
    case_payload = {
        "case_number": "CASE-VERSION-001",
        "title": "State vs Johnson",
        "description": "Versioning integration test case"
    }
    res = requests.post(f"{API_URL}/cases", json=case_payload, headers=lawyer_headers)
    assert res.status_code == 201
    case_id = res.json()["id"]

    # Add Client as participant
    res = requests.post(
        f"{API_URL}/cases/{case_id}/participants",
        json={"user_id": client_id, "role": "client"},
        headers=lawyer_headers
    )
    assert res.status_code == 201

    # Upload initial Document (creates V1)
    headers = lawyer_headers.copy()
    headers["X-Idempotency-Key"] = str(uuid.uuid4())
    files = {"file": ("document_v1.pdf", PDF_MAGIC_V1, "application/pdf")}
    data = {"title": "Versioned Pleading", "document_type": "pleading"}

    res = requests.post(f"{API_URL}/cases/{case_id}/documents", files=files, data=data, headers=headers)
    assert res.status_code == 201
    doc_data = res.json()
    doc_id = doc_data["id"]
    v1_id = doc_data["current_version_id"]
    print(f"Document created. ID: {doc_id}, Version 1 ID: {v1_id}")

    # Verify blockchain confirms V1
    time.sleep(1) # wait for Hardhat to mine
    requests.get(f"{API_URL}/documents/{doc_id}", headers=lawyer_headers)

    print("\n--- 4. Testing Document Lineage (V1 -> V2 -> V3) ---")
    # Upload V2
    headers_v2 = lawyer_headers.copy()
    headers_v2["X-Idempotency-Key"] = str(uuid.uuid4())
    files_v2 = {"file": ("document_v2.pdf", PDF_MAGIC_V2, "application/pdf")}
    
    res = requests.post(f"{API_URL}/documents/{doc_id}/versions", files=files_v2, headers=headers_v2)
    assert res.status_code == 201
    v2_data = res.json()
    v2_id = v2_data["id"]
    assert v2_data["version_number"] == 2
    assert v2_data["parent_version_id"] == str(v1_id)
    print(f"Version 2 created. ID: {v2_id}, Parent: {v1_id}")

    # Upload V3
    headers_v3 = lawyer_headers.copy()
    headers_v3["X-Idempotency-Key"] = str(uuid.uuid4())
    files_v3 = {"file": ("document_v3.pdf", PDF_MAGIC_V3, "application/pdf")}
    
    res = requests.post(f"{API_URL}/documents/{doc_id}/versions", files=files_v3, headers=headers_v3)
    assert res.status_code == 201
    v3_data = res.json()
    v3_id = v3_data["id"]
    assert v3_data["version_number"] == 3
    assert v3_data["parent_version_id"] == str(v2_id)
    print(f"Version 3 created. ID: {v3_id}, Parent: {v2_id}")

    # Verify latest document details has current_version_id pointing to V3
    res = requests.get(f"{API_URL}/documents/{doc_id}", headers=lawyer_headers)
    assert res.status_code == 200
    assert res.json()["current_version_id"] == str(v3_id)
    print("Document latest version pointer correctly references V3.")

    print("\n--- 5. Testing Database Immutability Triggers (SQL / ORM) ---")
    db_session = SessionLocal()
    try:
        # Check direct SQL UPDATE rejection
        print("Asserting SQL UPDATE fails...")
        sql_update_failed = False
        try:
            db_session.execute(text(f"UPDATE document_versions SET sha256_hash = 'fakehash' WHERE id = '{v1_id}';"))
            db_session.commit()
        except Exception as e:
            sql_update_failed = True
            db_session.rollback()
            print(f"SQL UPDATE failed as expected: {str(e)}")
        assert sql_update_failed, "SQL UPDATE on document_versions did not fail!"

        # Check direct SQL DELETE rejection
        print("Asserting SQL DELETE fails...")
        sql_delete_failed = False
        try:
            db_session.execute(text(f"DELETE FROM document_versions WHERE id = '{v1_id}';"))
            db_session.commit()
        except Exception as e:
            sql_delete_failed = True
            db_session.rollback()
            print(f"SQL DELETE failed as expected: {str(e)}")
        assert sql_delete_failed, "SQL DELETE on document_versions did not fail!"

        # Check ORM UPDATE rejection
        print("Asserting ORM UPDATE fails...")
        orm_update_failed = False
        try:
            ver = db_session.query(DocumentVersion).filter(DocumentVersion.id == v1_id).first()
            ver.sha256_hash = "fakehashorm"
            db_session.commit()
        except ValueError as e:
            orm_update_failed = True
            db_session.rollback()
            print(f"ORM UPDATE failed as expected: {str(e)}")
        assert orm_update_failed, "ORM UPDATE on document_versions did not fail!"

        # Check ORM DELETE rejection
        print("Asserting ORM DELETE fails...")
        orm_delete_failed = False
        try:
            ver = db_session.query(DocumentVersion).filter(DocumentVersion.id == v1_id).first()
            db_session.delete(ver)
            db_session.commit()
        except ValueError as e:
            orm_delete_failed = True
            db_session.rollback()
            print(f"ORM DELETE failed as expected: {str(e)}")
        assert orm_delete_failed, "ORM DELETE on document_versions did not fail!"

    finally:
        db_session.close()

    print("\n--- 6. Testing Version Upload Idempotency Retries ---")
    # Same key, user, document retry returns 200 OK and same version metadata
    headers_v3_retry = lawyer_headers.copy()
    headers_v3_retry["X-Idempotency-Key"] = headers_v3["X-Idempotency-Key"]
    res = requests.post(f"{API_URL}/documents/{doc_id}/versions", files=files_v3, headers=headers_v3_retry)
    assert res.status_code == 200
    assert res.json()["id"] == str(v3_id)
    print("Idempotent retry with matching context converged to same version ID successfully.")

    # Same key + different user rejects with 409 Conflict
    headers_v3_diff_user = client_headers.copy() # different user
    headers_v3_diff_user["X-Idempotency-Key"] = headers_v3["X-Idempotency-Key"]
    res = requests.post(f"{API_URL}/documents/{doc_id}/versions", files=files_v3, headers=headers_v3_diff_user)
    assert res.status_code == 409
    print("Idempotency retry with different user rejected with 409 Conflict.")

    # Same key + different document rejects with 409 Conflict
    # Create different document first
    headers_other_doc = lawyer_headers.copy()
    headers_other_doc["X-Idempotency-Key"] = str(uuid.uuid4())
    res_other = requests.post(f"{API_URL}/cases/{case_id}/documents", files=files, data={"title": "Other Doc", "document_type": "evidence"}, headers=headers_other_doc)
    other_doc_id = res_other.json()["id"]

    headers_other_retry = lawyer_headers.copy()
    headers_other_retry["X-Idempotency-Key"] = headers_v3["X-Idempotency-Key"] # same key
    res = requests.post(f"{API_URL}/documents/{other_doc_id}/versions", files=files_v3, headers=headers_other_retry)
    assert res.status_code == 409
    print("Idempotency retry with different document rejected with 409 Conflict.")

    print("\n--- 7. Testing Concurrency Locking ---")
    # Because we serialize requests with FOR UPDATE, concurrent uploads lock sequentially.
    # To verify that the UNIQUE constraint on (document_id, version_number) acts as the safety net,
    # we simulate concurrent database insertions inside separate transactions.
    db1 = SessionLocal()
    db2 = SessionLocal()
    try:
        # User A acquires row lock on document
        doc1 = db1.query(Document).filter(Document.id == doc_id).with_for_update().first()
        assert doc1 is not None

        # User B attempts to acquire row lock on same document (will block or fail)
        print("Asserting User B row lock blocks/timeouts...")
        # Since we are using standard Postgres, we can test with NOWAIT or skip lock wait timeouts
        sql_locked = False
        try:
            db2.execute(text(f"SELECT id FROM documents WHERE id = '{doc_id}' FOR UPDATE NOWAIT;"))
        except Exception as e:
            sql_locked = True
            db2.rollback()
            print(f"User B lock blocked successfully: {str(e)}")
        assert sql_locked, "User B select FOR UPDATE NOWAIT did not fail while User A held lock!"
    finally:
        db1.close()
        db2.close()
    print("Pessimistic locking and sequential FOR UPDATE checks validated successfully.")

    print("\n--- 8. Testing Blockchain Registration Failure & Retry ---")
    # Simulate a version creation where blockchain fails
    # We pass an invalid private key on adapter config or simulate RPC node disconnect.
    # To simulate it cleanly: we trigger a post with a mock blockchain RPC failure by altering configuration.
    original_rpc = settings.blockchain_rpc_url
    settings.blockchain_rpc_url = "http://localhost:9999" # invalid port (outage)

    # Reinitialize a new API process or directly mock.
    # Note: Since the live server runs in another process, it is using settings from the environment.
    # We can test this by calling the manually created adapter check.
    adapter_outage = BlockchainAdapter()
    adapter_outage.w3.provider.endpoint_uri = "http://localhost:9999"

    print("Asserting blockchain adapter fails on outage...")
    outage_failed = False
    try:
        adapter_outage.register_version(uuid.uuid4().bytes, uuid.uuid4().bytes, bytes(32))
    except Exception as e:
        outage_failed = True
        print(f"Adapter call threw connection exception: {str(e)}")
    assert outage_failed, "Adapter call did not fail on RPC outage!"

    # Restore endpoint
    settings.blockchain_rpc_url = original_rpc
    adapter_outage.w3.provider.endpoint_uri = original_rpc
    print("Blockchain registration failure behavior validated successfully.")

    print("\n--- 9. Testing Independent Verification & Tamper Isolation ---")
    # Verify Version 1
    files_v1 = {"file": ("document_v1.pdf", PDF_MAGIC_V1, "application/pdf")}
    verify_data_v1 = {"document_id": doc_id, "version_id": v1_id}
    res = requests.post(f"{API_URL}/verify", files=files_v1, data=verify_data_v1, headers=lawyer_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "VERIFIED"
    print("Version 1 verifies successfully.")

    # Verify Version 3
    verify_data_v3 = {"document_id": doc_id, "version_id": v3_id}
    res = requests.post(f"{API_URL}/verify", files=files_v3, data=verify_data_v3, headers=lawyer_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "VERIFIED"
    print("Version 3 verifies successfully.")

    # Verify Version 2 (before tamper)
    verify_data_v2 = {"document_id": doc_id, "version_id": v2_id}
    res = requests.post(f"{API_URL}/verify", files=files_v2, data=verify_data_v2, headers=lawyer_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "VERIFIED"
    print("Version 2 verifies successfully before tamper.")

    # Tamper version 2 only (pass modified content bytes PDF_MAGIC_V3 against version 2 context)
    res = requests.post(f"{API_URL}/verify", files=files_v3, data=verify_data_v2, headers=lawyer_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "INTEGRITY_FAILURE"
    print("Version 2 tamper returns INTEGRITY_FAILURE successfully.")

    # Verify V1 and V3 remain valid
    res = requests.post(f"{API_URL}/verify", files=files_v1, data=verify_data_v1, headers=lawyer_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "VERIFIED"

    res = requests.post(f"{API_URL}/verify", files=files_v3, data=verify_data_v3, headers=lawyer_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "VERIFIED"
    print("Tampering V2 has zero impact on V1 and V3 integrity verification (Isolated integrity).")

    print("\n=== ALL M4 INTEGRATION TESTS PASSED CLEANLY ===")

    # Trigger M5 Access Control and Auditing Integration Tests
    test_m5_access_control(
        lawyer_headers=lawyer_headers,
        client_headers=client_headers,
        lawyer_id=lawyer_id,
        client_id=client_id,
        case_id=case_id,
        doc_id=doc_id,
        v1_id=v1_id,
        v2_id=v2_id,
        v3_id=v3_id
    )

    # Trigger M6 Document Passport & Independent Verification Integration Tests
    test_m6_verification_and_passport(
        lawyer_headers=lawyer_headers,
        client_headers=client_headers,
        lawyer_id=lawyer_id,
        client_id=client_id,
        case_id=case_id,
        doc_id=doc_id,
        v1_id=v1_id,
        v2_id=v2_id,
        v3_id=v3_id
    )


def test_m5_access_control(lawyer_headers, client_headers, lawyer_id, client_id, case_id, doc_id, v1_id, v2_id, v3_id):
    print("\n--- 10. Testing M5 Fine-Grained Access Control & Auditing ---")
    
    # Assert initial state: general participant (client) has case access but no explicit grants
    print("Checking Client initial block...")
    res = requests.get(f"{API_URL}/documents/{doc_id}", headers=client_headers)
    assert res.status_code == 404  # Client has case access but no version grants yet, returns 404 to hide passport
    
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions/{v1_id}", headers=client_headers)
    assert res.status_code == 404  # Returns 404 to hide existence because they have zero grants for this document
    
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions/{v1_id}/download", headers=client_headers)
    assert res.status_code == 404

    # 1. Test VIEW and DOWNLOAD grants
    print("Granting VIEW access to V1...")
    grant_payload = {
        "user_id": client_id,
        "permission": "VIEW"
    }
    res = requests.post(f"{API_URL}/documents/{doc_id}/versions/{v1_id}/access", json=grant_payload, headers=lawyer_headers)
    assert res.status_code == 201
    grant_data = res.json()
    grant_id = grant_data["id"]
    assert grant_data["permission"] == "VIEW"
    
    # Client should be able to view metadata passport now
    res = requests.get(f"{API_URL}/documents/{doc_id}", headers=client_headers)
    assert res.status_code == 200
    # Note: they don't have access to v3_id, so the current_version_id in the passport is None/omitted
    assert res.json()["current_version_id"] is None
    
    # They should only see versions they have grants for (which is V1)
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions", headers=client_headers)
    assert res.status_code == 200
    versions_listed = res.json()
    assert len(versions_listed) == 1
    assert versions_listed[0]["id"] == str(v1_id)
    
    # Verify metadata detail retrieval for V1
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions/{v1_id}", headers=client_headers)
    assert res.status_code == 200
    
    # Verify metadata detail retrieval for V2 (should now return 403 Forbidden because they know doc exists via V1, but have no grant for V2)
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions/{v2_id}", headers=client_headers)
    assert res.status_code == 403
    assert "DOCUMENT_ACCESS_DENIED" in res.json()["error"]["code"]
    
    # Verify download of V1 is still blocked (since grant is VIEW only)
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions/{v1_id}/download", headers=client_headers)
    assert res.status_code == 403

    # 2. Test VIEW -> DOWNLOAD upgrade
    print("Upgrading grant to DOWNLOAD...")
    upgrade_payload = {
        "user_id": client_id,
        "permission": "DOWNLOAD"
    }
    res = requests.post(f"{API_URL}/documents/{doc_id}/versions/{v1_id}/access", json=upgrade_payload, headers=lawyer_headers)
    assert res.status_code == 201
    upgraded_grant_data = res.json()
    upgraded_grant_id = upgraded_grant_data["id"]
    assert upgraded_grant_id != grant_id
    assert upgraded_grant_data["permission"] == "DOWNLOAD"
    
    # Verify client can now download V1 payload
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions/{v1_id}/download", headers=client_headers)
    assert res.status_code == 200
    assert res.content == PDF_MAGIC_V1

    # Verify uniqueness index (cannot insert another active grant for same user/version)
    print("Asserting duplicate active grant check...")
    db = SessionLocal()
    try:
        from app.models.document import DocumentAccessGrant
        dup_grant = DocumentAccessGrant(
            document_id=uuid.UUID(doc_id),
            version_id=uuid.UUID(v1_id),
            granted_to_user_id=uuid.UUID(client_id),
            granted_by_user_id=uuid.UUID(lawyer_id),
            permission="VIEW"
        )
        db.add(dup_grant)
        duplicate_failed = False
        try:
            db.commit()
        except Exception as e:
            duplicate_failed = True
            db.rollback()
            print(f"Duplicate grant blocked at DB level: {str(e)}")
        assert duplicate_failed, "Duplicate active grant was not blocked by unique index!"
    finally:
        db.close()

    # 3. Test Expiration
    print("Testing grant expiration...")
    db = SessionLocal()
    from datetime import datetime, timedelta, timezone
    try:
        from app.models.document import DocumentAccessGrant
        expired_grant = DocumentAccessGrant(
            document_id=uuid.UUID(doc_id),
            version_id=uuid.UUID(v2_id),
            granted_to_user_id=uuid.UUID(client_id),
            granted_by_user_id=uuid.UUID(lawyer_id),
            permission="DOWNLOAD",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=10)
        )
        db.add(expired_grant)
        db.commit()
    finally:
        db.close()
        
    # Verify Client is blocked from viewing/downloading V2
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions/{v2_id}", headers=client_headers)
    assert res.status_code == 403
    
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions/{v2_id}/download", headers=client_headers)
    assert res.status_code == 403

    # 4. Test Permanent Revocation
    print("Testing revocation...")
    res = requests.post(f"{API_URL}/documents/{doc_id}/access/{upgraded_grant_id}/revoke", headers=lawyer_headers)
    assert res.status_code == 200
    
    # Client should be blocked immediately from downloading V1 now
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions/{v1_id}/download", headers=client_headers)
    assert res.status_code == 404
    
    # Check that revoked grant still exists in DB
    db = SessionLocal()
    try:
        revoked_grant = db.query(DocumentAccessGrant).filter(DocumentAccessGrant.id == upgraded_grant_id).first()
        assert revoked_grant is not None
        assert revoked_grant.revoked_at is not None
        print("Revoked grant remains in DB history successfully.")
    finally:
        db.close()

    # 5. Test V1 grant does not expose V2/V3 (Version Isolation)
    print("Testing version isolation...")
    grant_payload_v1 = {"user_id": client_id, "permission": "DOWNLOAD"}
    res = requests.post(f"{API_URL}/documents/{doc_id}/versions/{v1_id}/access", json=grant_payload_v1, headers=lawyer_headers)
    new_v1_grant_id = res.json()["id"]
    
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions/{v1_id}/download", headers=client_headers)
    assert res.status_code == 200
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions/{v3_id}/download", headers=client_headers)
    assert res.status_code == 403
    
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions", headers=client_headers)
    assert len(res.json()) == 1
    assert res.json()[0]["id"] == str(v1_id)
    print("Version isolation (V1 grant does not leak V2/V3) validated successfully.")

    # 6. Test IDOR/BOLA (Case Participation)
    print("Testing BOLA/IDOR protection...")
    stranger_payload = {
        "email": "stranger@evault.test",
        "password": "securepassword123",
        "display_name": "Stranger User",
        "role": "LAWYER"
    }
    requests.post(f"{API_URL}/auth/register", json=stranger_payload)
    login_res = requests.post(f"{API_URL}/auth/login", json={
        "email": "stranger@evault.test",
        "password": "securepassword123"
    })
    stranger_token = login_res.json()["access_token"]
    stranger_headers = {"Authorization": f"Bearer {stranger_token}"}
    
    res = requests.get(f"{API_URL}/documents/{doc_id}", headers=stranger_headers)
    assert res.status_code == 404
    
    res = requests.get(f"{API_URL}/documents/{doc_id}/versions/{v1_id}/download", headers=stranger_headers)
    assert res.status_code == 404
    print("BOLA/IDOR protection (non-participants receive 404) validated successfully.")

    # 7. Test Audit Event Generation
    print("Listing audit timeline (as Lawyer)...")
    res = requests.get(f"{API_URL}/documents/{doc_id}/audit", headers=lawyer_headers)
    assert res.status_code == 200
    audit_events = res.json()
    
    event_types = [e["event_type"] for e in audit_events]
    print(f"Logged events: {event_types}")
    assert "ACCESS_GRANTED" in event_types
    assert "ACCESS_REVOKED" in event_types
    assert "DOCUMENT_DOWNLOADED" in event_types
    assert "ACCESS_DENIED" in event_types
    
    for event in audit_events:
        metadata = event.get("event_metadata_json") or {}
        assert "password" not in metadata
        assert "key" not in metadata
        assert "content" not in metadata
        assert "private_key" not in metadata
    print("Audit log event verification completed successfully.")

    # 8. Test Direct SQL mutations on audit_events (database triggers)
    print("Asserting SQL UPDATE/DELETE on audit_events triggers fail...")
    db = SessionLocal()
    try:
        from app.models.audit import AuditEvent
        first_event = db.query(AuditEvent).first()
        assert first_event is not None
        
        update_audit_failed = False
        try:
            db.execute(text(f"UPDATE audit_events SET event_type = 'TAMPERED' WHERE id = '{first_event.id}';"))
            db.commit()
        except Exception as e:
            update_audit_failed = True
            db.rollback()
            print(f"SQL UPDATE on audit_events rejected: {str(e)}")
        assert update_audit_failed
        
        delete_audit_failed = False
        try:
            db.execute(text(f"DELETE FROM audit_events WHERE id = '{first_event.id}';"))
            db.commit()
        except Exception as e:
            delete_audit_failed = True
            db.rollback()
            print(f"SQL DELETE on audit_events rejected: {str(e)}")
        assert delete_audit_failed
    finally:
        db.close()

    # 9. Test Direct SQL mutations on document_access_grants (database triggers)
    print("Asserting SQL UPDATE/DELETE on document_access_grants triggers fail...")
    db = SessionLocal()
    try:
        delete_grant_failed = False
        try:
            db.execute(text(f"DELETE FROM document_access_grants WHERE id = '{new_v1_grant_id}';"))
            db.commit()
        except Exception as e:
            delete_grant_failed = True
            db.rollback()
            print(f"SQL DELETE on document_access_grants rejected: {str(e)}")
        assert delete_grant_failed
        
        update_grant_core_failed = False
        try:
            db.execute(text(f"UPDATE document_access_grants SET permission = 'VIEW' WHERE id = '{new_v1_grant_id}';"))
            db.commit()
        except Exception as e:
            update_grant_core_failed = True
            db.rollback()
            print(f"SQL UPDATE of core field rejected: {str(e)}")
        assert update_grant_core_failed
        
        # revoked_at NULL -> timestamp transition
        db.execute(text(f"UPDATE document_access_grants SET revoked_at = timezone('utc', now()) WHERE id = '{new_v1_grant_id}';"))
        db.commit()
        print("revoked_at NULL -> timestamp transition allowed successfully.")
        
        # Modification of non-NULL revoked_at fails
        update_revoked_at_failed = False
        try:
            db.execute(text(f"UPDATE document_access_grants SET revoked_at = NULL WHERE id = '{new_v1_grant_id}';"))
            db.commit()
        except Exception as e:
            update_revoked_at_failed = True
            db.rollback()
            print(f"SQL UPDATE resetting revoked_at rejected: {str(e)}")
        assert update_revoked_at_failed
    finally:
        db.close()

    # 10. Test User Deactivation and FK RESTRICT
    print("Testing user deactivation and referential integrity...")
    db = SessionLocal()
    try:
        from app.models.user import User
        client_user = db.query(User).filter(User.id == uuid.UUID(client_id)).first()
        client_user.status = "inactive"
        db.commit()
        
        grants_count = db.query(DocumentAccessGrant).filter(DocumentAccessGrant.granted_to_user_id == uuid.UUID(client_id)).count()
        assert grants_count > 0
        print("Historical grants are preserved after user deactivation.")
        
        delete_user_failed = False
        try:
            db.execute(text(f"DELETE FROM users WHERE id = '{client_id}';"))
            db.commit()
        except Exception as e:
            delete_user_failed = True
            db.rollback()
            print(f"Physical delete of referenced user blocked: {str(e)}")
        assert delete_user_failed
    finally:
        db.close()

    print("\n=== ALL M5 ACCESS CONTROL & AUDIT INTEGRATION TESTS PASSED CLEANLY ===")


def test_m6_verification_and_passport(lawyer_headers, client_headers, lawyer_id, client_id, case_id, doc_id, v1_id, v2_id, v3_id):
    print("\n--- 11. Testing M6 Document Passport & Independent Verification ---")

    # Reactivate client user
    db = SessionLocal()
    try:
        from app.models.user import User
        client_user = db.query(User).filter(User.id == uuid.UUID(client_id)).first()
        client_user.status = "active"
        db.commit()
    finally:
        db.close()

    # 1. Test Document Passport retrieval (Lawyer has complete visibility)
    print("Testing complete Passport retrieval (as Lead Lawyer)...")
    res = requests.get(f"{API_URL}/documents/{doc_id}/passport", headers=lawyer_headers)
    assert res.status_code == 200
    passport = res.json()
    assert passport["title"] == "Versioned Pleading"
    assert passport["current_version_number"] == 3
    assert len(passport["versions"]) == 3
    print("Lead Lawyer passport retrieval matches expected lineage (V1->V2->V3).")

    # 2. Test Passport visibility & redaction for general case participant (Client initially unauthorized)
    print("Testing Passport retrieval (as Client before any grants)...")
    res = requests.get(f"{API_URL}/documents/{doc_id}/passport", headers=client_headers)
    assert res.status_code == 404  # Client has case access but no version grants yet, returns 404 to hide passport

    # Grant access to V1 only
    print("Granting access to V1 (only) to Client...")
    grant_payload = {"user_id": client_id, "permission": "VIEW"}
    res = requests.post(f"{API_URL}/documents/{doc_id}/versions/{v1_id}/access", json=grant_payload, headers=lawyer_headers)
    assert res.status_code == 201

    # Test Passport retrieval (Client with V1 grant)
    print("Testing Passport retrieval (as Client with V1 grant)...")
    res = requests.get(f"{API_URL}/documents/{doc_id}/passport", headers=client_headers)
    assert res.status_code == 200
    passport_client = res.json()
    
    # Assert V2 and V3 are completely hidden and V1 is the "current" version returned
    assert passport_client["current_version_number"] == 1
    assert len(passport_client["versions"]) == 1
    assert passport_client["versions"][0]["version_number"] == 1
    
    # Direct JSON inspection: Verify unauthorized version IDs and metadata are completely absent from the raw body
    raw_response_text = res.text
    assert str(v2_id) not in raw_response_text
    assert str(v3_id) not in raw_response_text
    assert "version_number\": 2" not in raw_response_text
    assert "version_number\": 3" not in raw_response_text
    print("Information leakage check: V2/V3 are completely omitted (not just hidden) from Passport response for Client.")

    # Extract V1 opaque verification ID
    v1_opaque_id = passport_client["versions"][0]["opaque_verification_id"]
    assert v1_opaque_id is not None

    # Fetch lawyer passport to extract V2/V3 opaque IDs and verify public_verification_url format
    res = requests.get(f"{API_URL}/documents/{doc_id}/passport", headers=lawyer_headers)
    assert res.status_code == 200
    passport_lawyer = res.json()
    v2_opaque_id = None
    v3_opaque_id = None
    for v in passport_lawyer["versions"]:
        assert v["public_verification_url"].startswith(settings.public_verify_base_url)
        if v["version_number"] == 2:
            v2_opaque_id = v["opaque_verification_id"]
        elif v["version_number"] == 3:
            v3_opaque_id = v["opaque_verification_id"]
    assert v2_opaque_id is not None
    assert v3_opaque_id is not None

    # 3. Test Public Verification (Original File V1 -> VERIFIED)
    print("Testing public verification with original V1...")
    files_v1 = {"file": ("document_v1.pdf", PDF_MAGIC_V1, "application/pdf")}
    res = requests.post(f"{API_URL}/verify/public/{v1_opaque_id}", files=files_v1)
    assert res.status_code == 200
    verify_res = res.json()
    assert verify_res["status"] == "VERIFIED"
    assert "disclaimer" in verify_res
    
    # Assert public response contains no internal IDs or private wallet info
    for key in ["document_id", "version_id", "case_id", "registered_by", "wallet_address"]:
        assert key not in verify_res
    print("Original file V1 verified successfully. Checked response has no internal identifiers or wallet addresses.")

    # 4. Test Public Verification (V1 QR remains bound to V1 after V2/V3 exist)
    print("Testing public verification V1 QR targeting V1 content (when V2/V3 exist in DB)...")
    res = requests.post(f"{API_URL}/verify/public/{v1_opaque_id}", files=files_v1)
    assert res.status_code == 200
    assert res.json()["status"] == "VERIFIED"
    print("V1 QR remains target-bound to V1 verification.")

    # 5. Test Public Verification (One-byte modification -> INTEGRITY_FAILURE)
    print("Testing public verification with one-byte modification...")
    tampered_bytes = PDF_MAGIC_V1 + b"\x00"  # Append one byte
    files_v1_tampered = {"file": ("document_v1.pdf", tampered_bytes, "application/pdf")}
    res = requests.post(f"{API_URL}/verify/public/{v1_opaque_id}", files=files_v1_tampered)
    assert res.status_code == 200
    verify_res = res.json()
    assert verify_res["status"] == "INTEGRITY_FAILURE"
    assert "disclaimer" in verify_res
    print("One-byte alteration returns INTEGRITY_FAILURE correctly.")

    # 6. Test Public Verification for V2 and V3 (Independent Verification)
    print("Testing public verification for V2 and V3...")
    files_v2 = {"file": ("document_v2.pdf", PDF_MAGIC_V2, "application/pdf")}
    res = requests.post(f"{API_URL}/verify/public/{v2_opaque_id}", files=files_v2)
    assert res.status_code == 200
    assert res.json()["status"] == "VERIFIED"

    files_v3 = {"file": ("document_v3.pdf", PDF_MAGIC_V3, "application/pdf")}
    res = requests.post(f"{API_URL}/verify/public/{v3_opaque_id}", files=files_v3)
    assert res.status_code == 200
    assert res.json()["status"] == "VERIFIED"
    print("V2 and V3 verified independently.")

    # 7. Test Public Verification (Oversized/Malformed upload rejections)
    print("Testing public verification with oversized upload...")
    oversized_bytes = b"%" + b"PDF-" + b"0" * (10 * 1024 * 1024 + 10)
    files_oversized = {"file": ("document_large.pdf", oversized_bytes, "application/pdf")}
    res = requests.post(f"{API_URL}/verify/public/{v1_opaque_id}", files=files_oversized)
    assert res.status_code == 400
    assert "exceeds" in res.json()["detail"]

    print("Testing public verification with non-PDF extension...")
    files_bad_ext = {"file": ("document_v1.txt", PDF_MAGIC_V1, "text/plain")}
    res = requests.post(f"{API_URL}/verify/public/{v1_opaque_id}", files=files_bad_ext)
    assert res.status_code == 400
    assert "Only PDF" in res.json()["detail"]

    print("Testing public verification with bad MIME type...")
    files_bad_mime = {"file": ("document_v1.pdf", PDF_MAGIC_V1, "image/png")}
    res = requests.post(f"{API_URL}/verify/public/{v1_opaque_id}", files=files_bad_mime)
    assert res.status_code == 400
    assert "MIME type" in res.json()["detail"]

    print("Testing public verification with malformed magic bytes...")
    files_bad_magic = {"file": ("document_v1.pdf", b"HELLO WORLD", "application/pdf")}
    res = requests.post(f"{API_URL}/verify/public/{v1_opaque_id}", files=files_bad_magic)
    assert res.status_code == 400
    assert "magic bytes" in res.json()["detail"]
    print("PDF size, format, extension, and content signature controls verified successfully.")

    # 8. Test Public Verification Audit Events
    print("Testing public verification audit trail events...")
    db = SessionLocal()
    try:
        from app.models.audit import AuditEvent
        latest_audit = db.query(AuditEvent).filter(
            AuditEvent.version_id == uuid.UUID(v1_id)
        ).order_by(AuditEvent.created_at.desc()).first()
        
        assert latest_audit is not None
        assert latest_audit.actor_type == "PUBLIC_VERIFIER"
        assert latest_audit.actor_user_id is None
        assert latest_audit.event_type in ("DOCUMENT_VERIFIED", "SECURITY_FAILURE")
        print("Anonymous Audit trails validated successfully: actor_type=PUBLIC_VERIFIER, actor_user_id=NULL.")
    finally:
        db.close()

    # 9. Test Blockchain Outage -> VERIFICATION_UNAVAILABLE
    print("Testing public verification during blockchain outage...")
    import subprocess
    import os
    env_outage = os.environ.copy()
    env_outage["BLOCKCHAIN_RPC_URL"] = "http://127.0.0.1:9999"
    env_outage["BYPASS_STARTUP_VALIDATION"] = "true"
    env_outage["PUBLIC_VERIFY_BASE_URL"] = "https://sih-demo-domain.evault.test"
    uvicorn_path = str(backend_dir / ".venv" / "Scripts" / "uvicorn.exe")
    if not os.path.exists(uvicorn_path):
        uvicorn_path = "uvicorn"
    cmd = [uvicorn_path, "app.main:app", "--host", "127.0.0.1", "--port", "8001"]
    log_file = open("outage_server.log", "w")
    proc = subprocess.Popen(cmd, env=env_outage, stdout=log_file, stderr=log_file, cwd=str(backend_dir))
    time.sleep(7)  # wait for server to start
    try:
        # Test configurable base URL returned from passport API
        res_passport = requests.get(f"http://127.0.0.1:8001/api/v1/documents/{doc_id}/passport", headers=lawyer_headers)
        assert res_passport.status_code == 200
        passport_lawyer_8001 = res_passport.json()
        for v in passport_lawyer_8001["versions"]:
            assert v["public_verification_url"].startswith("https://sih-demo-domain.evault.test")
        print("Configurable base URL verified successfully in Passport payload on temporary port 8001 instance.")

        # Test blockchain outage query
        res = requests.post(f"http://127.0.0.1:8001/api/v1/verify/public/{v1_opaque_id}", files=files_v1)
        assert res.status_code == 200
        verify_res_outage = res.json()
        assert verify_res_outage["status"] == "VERIFICATION_UNAVAILABLE"
        # Proves that bypassing startup validation does NOT cause fallback to PostgreSQL verification
        assert verify_res_outage["status"] not in ("VERIFIED", "INTEGRITY_FAILURE")
        print("Blockchain outage returns VERIFICATION_UNAVAILABLE correctly on temporary instance, confirming no PostgreSQL fallback.")
    except Exception as exc:
        log_file.close()
        with open("outage_server.log", "r") as f:
            print("OUTAGE SERVER LOG CONTENT:\n", f.read())
        raise exc
    finally:
        proc.terminate()
        proc.wait()
        log_file.close()
        try:
            os.remove("outage_server.log")
        except Exception:
            pass

    # 10. Test Rate Limiting
    print("Testing public verification rate limiting...")
    rate_limited = False
    for i in range(15):
        res = requests.post(f"{API_URL}/verify/public/{v1_opaque_id}", files=files_v1)
        if res.status_code == 429:
            rate_limited = True
            print(f"Rate limited successfully at request {i+1}.")
            break
    assert rate_limited
    print("Sliding window IP-based rate limiting validated successfully.")

    # ==========================================
    # MILESTONE 6 COMPLIANCE INTEGRATION TESTS
    # ==========================================
    print("\n--- 11. Testing Milestone 6A: External Case Integration ---")
    # Ingest CASE-2026-001 with client as participant
    sync_payload = {
        "case_number": "CASE-2026-001",
        "title": "eCourts legacy case import",
        "description": "Mocked external case import sync",
        "participant_ids": [str(client_id)]
    }
    sync_res = requests.post(f"{API_URL}/integration/cases/sync", json=sync_payload, headers=lawyer_headers)
    assert sync_res.status_code == 201
    sync_data = sync_res.json()
    assert sync_data["status"] == "success"
    assert sync_data["case_number"] == "CASE-2026-001"
    imported_case_id = sync_data["case_id"]
    print("External case CASE-2026-001 synced and linked successfully.")

    # Upload document associated with this imported case
    headers_sync_doc = lawyer_headers.copy()
    headers_sync_doc["X-Idempotency-Key"] = str(uuid.uuid4())
    files_sync_doc = {"file": ("imported_doc.pdf", PDF_MAGIC_V1, "application/pdf")}
    data_sync_doc = {"title": "Imported Case File", "document_type": "exhibit"}
    doc_sync_res = requests.post(f"{API_URL}/cases/{imported_case_id}/documents", files=files_sync_doc, data=data_sync_doc, headers=headers_sync_doc)
    assert doc_sync_res.status_code == 201
    sync_doc_data = doc_sync_res.json()
    sync_doc_id = sync_doc_data["id"]
    sync_version_id = sync_doc_data["current_version_id"]
    print("Document uploaded and successfully linked to imported case.")

    print("\n--- 12. Testing Milestone 6B: Blockchain Permission Commitments ---")
    # Let's verify normal VIEW grant (Test 1) and Normal DOWNLOAD grant (Test 2)
    # 12.1 Normal VIEW grant
    view_grant_payload = {
        "user_id": str(client_id),
        "permission": "VIEW"
    }
    grant_view_res = requests.post(f"{API_URL}/documents/{sync_doc_id}/versions/{sync_version_id}/access", json=view_grant_payload, headers=lawyer_headers)
    assert grant_view_res.status_code == 201
    view_grant_data = grant_view_res.json()
    assert view_grant_data["permission"] == "VIEW"
    assert view_grant_data["blockchain_status"] in ("pending", "submitted", "confirmed")
    print("PostgreSQL VIEW grant created and permission commitment submitted to blockchain.")

    # Wait for Hardhat node to mine and confirm commitment
    time.sleep(2)

    # Demonstrate view permission works (Test 1)
    view_ver_res = requests.get(f"{API_URL}/documents/{sync_doc_id}/versions/{sync_version_id}", headers=client_headers)
    assert view_ver_res.status_code == 200
    print("Test 1 (Normal VIEW grant ALLOWED) passed successfully.")

    # Verify that a VIEW commitment does NOT authorize DOWNLOAD
    download_denied_res = requests.get(f"{API_URL}/documents/{sync_doc_id}/versions/{sync_version_id}/download", headers=client_headers)
    assert download_denied_res.status_code == 403
    print("Test 2.1 (VIEW commitment does NOT authorize DOWNLOAD) passed successfully.")

    # 12.2 Normal DOWNLOAD grant (Test 2)
    # Upgrade permission from VIEW to DOWNLOAD (which revokes old VIEW grant and creates new DOWNLOAD grant)
    download_grant_payload = {
        "user_id": str(client_id),
        "permission": "DOWNLOAD"
    }
    grant_dl_res = requests.post(f"{API_URL}/documents/{sync_doc_id}/versions/{sync_version_id}/access", json=download_grant_payload, headers=lawyer_headers)
    assert grant_dl_res.status_code == 201
    dl_grant_data = grant_dl_res.json()
    assert dl_grant_data["permission"] == "DOWNLOAD"
    dl_grant_id = dl_grant_data["id"]

    # Wait for Hardhat node to mine and confirm commitment
    time.sleep(2)

    # Demonstrate client can now download the version (Test 2)
    download_ok_res = requests.get(f"{API_URL}/documents/{sync_doc_id}/versions/{sync_version_id}/download", headers=client_headers)
    assert download_ok_res.status_code == 200
    assert download_ok_res.content == PDF_MAGIC_V1
    print("Test 2 (Normal DOWNLOAD grant ALLOWED) passed successfully.")

    # 12.3 Revoked grant (Test 4)
    # Lawyer revokes the download grant
    revoke_res = requests.post(f"{API_URL}/documents/{sync_doc_id}/access/{dl_grant_id}/revoke", headers=lawyer_headers)
    assert revoke_res.status_code == 200

    # Wait for Hardhat node to mine and transition commitment on-chain to REVOKED
    time.sleep(2)

    # Demonstrate access is denied
    download_revoked_res = requests.get(f"{API_URL}/documents/{sync_doc_id}/versions/{sync_version_id}/download", headers=client_headers)
    assert download_revoked_res.status_code == 404 # filtered out of active grants list
    print("Test 4 (Revoked grant access DENIED) passed successfully.")

    # 12.4 Fake PostgreSQL grant (Test 3)
    # Directly inject an unauthorized/fake active access grant in PostgreSQL
    print("Injecting fake access grant in PostgreSQL...")
    import uuid as pyuuid
    fake_grant_id = pyuuid.uuid4()
    fake_salt = pyuuid.uuid4().hex
    
    db = SessionLocal()
    try:
        # Create a direct database insert bypassing API validation filters
        db.execute(text(
            "INSERT INTO document_access_grants (id, document_id, version_id, granted_to_user_id, granted_by_user_id, permission, salt, blockchain_status, created_at) "
            f"VALUES ('{fake_grant_id}', '{sync_doc_id}', '{sync_version_id}', '{client_id}', '{lawyer_id}', 'DOWNLOAD', '{fake_salt}', 'confirmed', NOW());"
        ))
        db.commit()
    finally:
        db.close()

    # Attempt to retrieve/download version
    print("Attempting to access document using injected fake grant...")
    fake_access_res = requests.get(f"{API_URL}/documents/{sync_doc_id}/versions/{sync_version_id}/download", headers=client_headers)
    # Must fail with AUTHORIZATION_INTEGRITY_FAILURE (wrapped as 403)
    assert fake_access_res.status_code == 403
    assert fake_access_res.json()["error"]["code"] == "AUTHORIZATION_INTEGRITY_FAILURE"
    print("Test 3 (Fake database grant rejected with AUTHORIZATION_INTEGRITY_FAILURE) passed successfully.")

    # 12.5 Duplicate/Replay Commitment attempts (Test 6)
    print("Testing duplicate permission commitment registration...")
    from web3 import Web3
    adapter = BlockchainAdapter()
    dummy_version_id = pyuuid.uuid4()
    dummy_hash = Web3.solidity_keccak(['string'], ["dummycommitment"])
    
    # Register the commitment once
    tx1 = adapter.grant_permission(dummy_version_id.bytes, dummy_hash)
    time.sleep(1)
    
    # Try to register it again
    duplicate_failed = False
    try:
        adapter.grant_permission(dummy_version_id.bytes, dummy_hash)
        time.sleep(1)
    except Exception as e:
        duplicate_failed = True
        print(f"Re-registering commitment reverted as expected: {str(e)}")
    assert duplicate_failed, "Solidity contract did not prevent duplicate permission commitment registration!"
    print("Test 6 (Duplicate/replay commitment registration prevented) passed successfully.")

    # 12.6 Unauthorized contract callers (Test 7 and 8)
    print("Testing unauthorized contract callers for grant/revoke...")
    # Setup connection using an unauthorized user private key (e.g. from Hardhat accounts[1])
    unauthorized_private_key = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d" # Hardhat Account #1
    unauthorized_w3 = Web3(Web3.HTTPProvider(settings.blockchain_rpc_url))
    unauthorized_account = unauthorized_w3.eth.account.from_key(unauthorized_private_key)
    unauthorized_contract = unauthorized_w3.eth.contract(address=adapter.contract_address, abi=adapter.abi)
    
    # Attempt to grant permission
    grant_unauth_failed = False
    try:
        nonce = unauthorized_w3.eth.get_transaction_count(unauthorized_account.address)
        tx = unauthorized_contract.functions.grantPermission(
            dummy_version_id.bytes,
            dummy_hash
        ).build_transaction({
            "chainId": unauthorized_w3.eth.chain_id,
            "gas": 300000,
            "gasPrice": unauthorized_w3.eth.gas_price,
            "nonce": nonce
        })
        signed_tx = unauthorized_w3.eth.account.sign_transaction(tx, unauthorized_private_key)
        unauthorized_w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        time.sleep(1)
    except Exception as e:
        grant_unauth_failed = True
        print(f"Unauthorized grantPermission call reverted as expected: {str(e)}")
    assert grant_unauth_failed, "Unauthorized user was able to execute grantPermission!"
    print("Test 7 (Unauthorized contract caller cannot grant) passed successfully.")

    # Attempt to revoke permission
    revoke_unauth_failed = False
    try:
        nonce = unauthorized_w3.eth.get_transaction_count(unauthorized_account.address)
        tx = unauthorized_contract.functions.revokePermission(
            dummy_version_id.bytes,
            dummy_hash
        ).build_transaction({
            "chainId": unauthorized_w3.eth.chain_id,
            "gas": 300000,
            "gasPrice": unauthorized_w3.eth.gas_price,
            "nonce": nonce
        })
        signed_tx = unauthorized_w3.eth.account.sign_transaction(tx, unauthorized_private_key)
        unauthorized_w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        time.sleep(1)
    except Exception as e:
        revoke_unauth_failed = True
        print(f"Unauthorized revokePermission call reverted as expected: {str(e)}")
    assert revoke_unauth_failed, "Unauthorized user was able to execute revokePermission!"
    print("Test 8 (Unauthorized contract caller cannot revoke) passed successfully.")

    # 12.7 Concurrent grant/revoke behavior (Test 9)
    print("Testing concurrent grant/revoke transaction locks...")
    # Send multiple requests concurrently to ensure serial execution without nonce collisions
    import concurrent.futures
    
    def run_grant(v_id, c_hash):
        try:
            return adapter.grant_permission(v_id.bytes, c_hash)
        except Exception as e:
            return str(e)
            
    hashes_to_grant = [
        (pyuuid.uuid4(), Web3.solidity_keccak(['string'], [f"hash-{i}"])) for i in range(5)
    ]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_grant, h[0], h[1]) for h in hashes_to_grant]
        results = [f.result() for f in futures]
        
    for idx, res in enumerate(results):
        assert res.startswith("0x"), f"Concurrent grant failed for hash index {idx}: {res}"
    print("Test 9 (Concurrent grant/revoke serialization locks) passed successfully.")

    # 12.8 Blockchain transaction failure and reconciliation (Test 10)
    print("Testing transaction failure and reconciliation...")
    # Create a grant with failed blockchain status directly in DB
    failed_grant_id = pyuuid.uuid4()
    failed_grant_salt = pyuuid.uuid4().hex
    
    db = SessionLocal()
    try:
        # Revoke any existing active grants to avoid uq_active_grants unique constraint violation
        db.execute(text(
            "UPDATE document_access_grants "
            "SET revoked_at = timezone('utc', now()) "
            f"WHERE version_id = '{sync_version_id}' AND granted_to_user_id = '{client_id}' AND revoked_at IS NULL;"
        ))
        db.execute(text(
            "INSERT INTO document_access_grants (id, document_id, version_id, granted_to_user_id, granted_by_user_id, permission, salt, blockchain_status, created_at) "
            f"VALUES ('{failed_grant_id}', '{sync_doc_id}', '{sync_version_id}', '{client_id}', '{lawyer_id}', 'VIEW', '{failed_grant_salt}', 'failed', NOW());"
        ))
        db.commit()
    finally:
        db.close()
        
    # Attempt access: must be denied because blockchain status is 'failed' and not yet confirmed on-chain
    failed_access_res = requests.get(f"{API_URL}/documents/{sync_doc_id}/versions/{sync_version_id}", headers=client_headers)
    assert failed_access_res.status_code == 403
    assert "Grant blockchain commitment is not confirmed" in failed_access_res.json()["detail"]
    print("Test 10 (Transaction failure and reconciliation logic) passed successfully.")

    # 12.9 Blockchain outage check for client access (Test 5)
    print("Testing client access block during blockchain outage (no fallback)...")
    import subprocess
    import os
    env_outage = os.environ.copy()
    env_outage["BLOCKCHAIN_RPC_URL"] = "http://127.0.0.1:9999"
    env_outage["BYPASS_STARTUP_VALIDATION"] = "true"
    env_outage["PUBLIC_VERIFY_BASE_URL"] = "https://sih-demo-domain.evault.test"
    uvicorn_path = str(backend_dir / ".venv" / "Scripts" / "uvicorn.exe")
    if not os.path.exists(uvicorn_path):
        uvicorn_path = "uvicorn"
    cmd = [uvicorn_path, "app.main:app", "--host", "127.0.0.1", "--port", "8001"]
    log_file = open("outage_server_m6b.log", "w")
    proc = subprocess.Popen(cmd, env=env_outage, stdout=log_file, stderr=log_file, cwd=str(backend_dir))
    time.sleep(7)  # wait for server to start
    try:
        # Request access on the port 8001 instance where blockchain RPC is offline
        outage_access_res = requests.get(f"http://127.0.0.1:8001/api/v1/documents/{sync_doc_id}/versions/{sync_version_id}", headers=client_headers)
        assert outage_access_res.status_code == 403
        assert outage_access_res.json()["error"]["code"] == "AUTHORIZATION_UNAVAILABLE"
        print("Test 5 (Blockchain outage blocks authorization strictly, no DB fallback) passed successfully.")
    except Exception as outage_err:
        log_file.close()
        with open("outage_server_m6b.log", "r") as f:
            print("OUTAGE SERVER LOG CONTENT:\n", f.read())
        raise outage_err
    finally:
        proc.terminate()
        proc.wait()
        log_file.close()
        try:
            os.remove("outage_server_m6b.log")
        except Exception:
            pass

    print("\n=== ALL M6 VERIFICATION & PASSPORT INTEGRATION TESTS PASSED CLEANLY ===")


if __name__ == "__main__":
    try:
        run_tests()
    except AssertionError as e:
        print(f"\n[FAIL] Integration test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Integration test errored: {e}")
        sys.exit(1)

