from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.dependencies import get_current_user
from app.services.blockchain import BlockchainAdapter
from app.models.document import DocumentVersion
from app.models.audit import log_audit_event
from typing import Optional
import uuid
import hashlib
import logging
import time

logger = logging.getLogger("audit_events")
router = APIRouter(tags=["Verification"])

# Simple in-memory sliding window rate limiter
RATE_LIMIT_WINDOW = 60  # 1 minute
RATE_LIMIT_MAX_REQUESTS = 10
ip_request_history = {}

def check_rate_limit(client_ip: str) -> bool:
    now = time.time()
    if client_ip not in ip_request_history:
        ip_request_history[client_ip] = []
    
    # filter timestamps outside window
    ip_request_history[client_ip] = [t for t in ip_request_history[client_ip] if now - t < RATE_LIMIT_WINDOW]
    
    if len(ip_request_history[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return False
        
    ip_request_history[client_ip].append(now)
    return True


@router.post("/verify")
async def verify_document(
    file: UploadFile = File(...),
    document_id: uuid.UUID = Form(...),
    version_id: uuid.UUID = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verifies document integrity against the on-chain registry record for authenticated users.
    Candidate bytes -> SHA-256 -> contract registry query by versionId -> validation -> status.
    """
    # 1. Compute SHA-256 of candidate file bytes
    try:
        content_bytes = await file.read()
        candidate_hash = hashlib.sha256(content_bytes).hexdigest()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file bytes: {str(e)}"
        )

    # 2. Query Blockchain Adapter
    adapter = BlockchainAdapter()
    try:
        onchain_record = adapter.get_registration(version_id.bytes)
    except Exception as e:
        logger.error(f"Blockchain verification query failed: {str(e)}")
        # CRITICAL CONSTRAINT: Never return VERIFIED if blockchain check fails
        return {
            "status": "VERIFICATION_UNAVAILABLE",
            "message": "Blockchain registry is currently unreachable.",
            "disclaimer": "Verification confirms that the submitted file matches the cryptographic fingerprint registered for this record. It does not establish the legal validity, ownership, authenticity of underlying claims, or truthfulness of the document's contents."
        }

    # 3. Handle Record Not Found
    if not onchain_record:
        return {
            "status": "RECORD_NOT_FOUND",
            "message": "No provenance registration exists for this document version.",
            "disclaimer": "Verification confirms that the submitted file matches the cryptographic fingerprint registered for this record. It does not establish the legal validity, ownership, authenticity of underlying claims, or truthfulness of the document's contents."
        }

    # 4. Context Alignment Validation
    doc_id_match = onchain_record["document_id"] == document_id.bytes
    ver_id_match = onchain_record["version_id"] == version_id.bytes
    hash_match = onchain_record["sha256_hash"].lower() == candidate_hash.lower()

    if doc_id_match and ver_id_match and hash_match:
        logger.info(f"Audit Event: DOCUMENT_VERIFIED - Document ID: {document_id} - Version ID: {version_id} - Actor: {current_user.id}")
        return {
            "status": "VERIFIED",
            "message": "Document integrity and on-chain provenance verified successfully.",
            "block_number": onchain_record["block_number"],
            "timestamp": onchain_record["timestamp"],
            "registered_by": onchain_record["registered_by"],
            "disclaimer": "Verification confirms that the submitted file matches the cryptographic fingerprint registered for this record. It does not establish the legal validity, ownership, authenticity of underlying claims, or truthfulness of the document's contents."
        }
    else:
        logger.warning(
            f"Security Audit Failure: Document verification failed due to mismatch. "
            f"Expected Hash: {onchain_record['sha256_hash']}, Candidate: {candidate_hash}. "
            f"Expected Doc ID: {onchain_record['document_id'].hex()}, Candidate: {document_id.bytes.hex()}."
        )
        return {
            "status": "INTEGRITY_FAILURE",
            "message": "Integrity validation failed: document content or identity parameters mismatch.",
            "disclaimer": "Verification confirms that the submitted file matches the cryptographic fingerprint registered for this record. It does not establish the legal validity, ownership, authenticity of underlying claims, or truthfulness of the document's contents."
        }


@router.post("/verify/public/{opaque_verification_id}")
async def verify_document_public(
    opaque_verification_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Limited public verification using an opaque verification identifier.
    Does not require authentication. Verifies candidate document integrity.
    """
    # 1. Rate limiting check
    client_ip = "127.0.0.1"
    if request.client and request.client.host:
        client_ip = request.client.host

    if not check_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification requests. Please try again later."
        )

    # 2. Resolve opaque identifier
    version = db.query(DocumentVersion).filter(
        DocumentVersion.opaque_verification_id == opaque_verification_id
    ).first()
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opaque verification identifier not found."
        )

    # 3. File validations (Reusing M2 controls)
    max_size = 10 * 1024 * 1024
    try:
        content_bytes = await file.read()
        file_size = len(content_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file bytes: {str(e)}"
        )

    if file_size > max_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File size exceeds the 10MB limit.")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are supported.")

    # Accept application/pdf and application/octet-stream (some browsers/OS don't infer PDF MIME)
    ACCEPTED_CONTENT_TYPES = {"application/pdf", "application/octet-stream", "binary/octet-stream"}
    if file.content_type not in ACCEPTED_CONTENT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file MIME type.")

    if len(content_bytes) < 5 or content_bytes[:5] != b"%PDF-":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed PDF magic bytes.")

    # 4. SHA-256 Fingerprinting
    candidate_hash = hashlib.sha256(content_bytes).hexdigest()

    # 5. Query Blockchain Adapter
    adapter = BlockchainAdapter()
    try:
        onchain_record = adapter.get_registration(version.id.bytes)
    except Exception as e:
        logger.error(f"Blockchain public verification query failed: {str(e)}")
        # CRITICAL: Do NOT fall back to local database hashes
        return {
            "status": "VERIFICATION_UNAVAILABLE",
            "message": "Blockchain registry is currently unreachable.",
            "disclaimer": "Verification confirms that the submitted file matches the cryptographic fingerprint registered for this record. It does not establish the legal validity, ownership, authenticity of underlying claims, or truthfulness of the document's contents."
        }

    if not onchain_record:
        # DB version exists but no on-chain registry record found
        return {
            "status": "RECORD_NOT_FOUND",
            "message": "No provenance registration exists for this document version.",
            "disclaimer": "Verification confirms that the submitted file matches the cryptographic fingerprint registered for this record. It does not establish the legal validity, ownership, authenticity of underlying claims, or truthfulness of the document's contents."
        }

    # 6. Compare hash
    hash_match = onchain_record["sha256_hash"].lower() == candidate_hash.lower()

    # Log public audit event (with actor_type=PUBLIC_VERIFIER and actor_user_id=NULL)
    log_audit_event(
        event_type="DOCUMENT_VERIFIED" if hash_match else "SECURITY_FAILURE",
        actor_user_id=None,
        case_id=None,  # No case details in public event to protect privacy
        document_id=version.document_id,
        version_id=version.id,
        metadata={"result": "VERIFIED" if hash_match else "INTEGRITY_FAILURE"},
        actor_type="PUBLIC_VERIFIER"
    )

    if hash_match:
        logger.info(f"Public Audit Event: DOCUMENT_VERIFIED - Version ID: {version.id} - Source: Public Verification Portal")
        return {
            "status": "VERIFIED",
            "message": "Document integrity and on-chain provenance verified successfully.",
            "block_number": onchain_record["block_number"],
            "timestamp": onchain_record["timestamp"],
            "disclaimer": "Verification confirms that the submitted file matches the cryptographic fingerprint registered for this record. It does not establish the legal validity, ownership, authenticity of underlying claims, or truthfulness of the document's contents."
        }
    else:
        logger.warning(
            f"Public Security Audit Failure: Document verification failed due to mismatch. "
            f"Expected Hash: {onchain_record['sha256_hash']}, Candidate: {candidate_hash}."
        )
        return {
            "status": "INTEGRITY_FAILURE",
            "message": "Integrity validation failed: document content mismatch.",
            "disclaimer": "Verification confirms that the submitted file matches the cryptographic fingerprint registered for this record. It does not establish the legal validity, ownership, authenticity of underlying claims, or truthfulness of the document's contents."
        }
