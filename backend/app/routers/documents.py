from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Header, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.case import Case, CaseParticipant
from app.models.document import Document, DocumentVersion, DocumentAccessGrant
from app.models.audit import AuditEvent, log_audit_event
from app.schemas.document import (
    DocumentResponse, 
    DocumentDetailResponse, 
    DocumentVersionResponse,
    DocumentAccessGrantCreate,
    DocumentAccessGrantResponse,
    DocumentPassportResponse,
    DocumentPassportVersionInfo
)
from app.schemas.audit import AuditEventResponse
from app.dependencies import get_current_user
from app.services.kms import KMSService
from app.services.crypto import encrypt_bytes, decrypt_bytes
from app.services.storage import StorageService
from app.services.blockchain import BlockchainAdapter
from app.config import settings
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import hashlib
import io
import logging

logger = logging.getLogger("audit_events")
router = APIRouter(tags=["Documents"])

def verify_case_participant(case_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> bool:
    """
    Checks if a user is a registered participant in a case.
    """
    participant = db.query(CaseParticipant).filter(
        CaseParticipant.case_id == case_id,
        CaseParticipant.user_id == user_id
    ).first()
    return participant is not None


def is_lead_lawyer(case_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> bool:
    """
    Checks if a user has lead lawyer authorization for a case (creator or explicitly added with lead_lawyer role).
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return False
    if case.created_by == user_id:
        return True
    participant = db.query(CaseParticipant).filter(
        CaseParticipant.case_id == case_id,
        CaseParticipant.user_id == user_id
    ).first()
    return participant is not None and participant.role == "lead_lawyer"


def sync_grant_blockchain_status(grant: DocumentAccessGrant, db: Session):
    """
    Reconciles the PostgreSQL grant blockchain state with the EVM ledger state.
    """
    if grant.blockchain_status == "confirmed":
        return

    # If transaction hash is known, check transaction status
    if grant.blockchain_tx_hash:
        adapter = BlockchainAdapter()
        try:
            status_info = adapter.verify_transaction_status(grant.blockchain_tx_hash)
            if status_info:
                grant.blockchain_status = "confirmed"
                db.commit()
                return
        except Exception:
            pass

    # Check contract registry directly using the salted hash
    from web3 import Web3
    adapter = BlockchainAdapter()
    
    version_bytes = grant.version_id.bytes
    grantee_bytes = grant.granted_to_user_id.bytes
    perm_bytes = grant.permission.encode('utf-8')
    salt_bytes = bytes.fromhex(grant.salt)

    expected_hash = Web3.solidity_keccak(
        ['bytes16', 'bytes16', 'bytes', 'bytes16'],
        [version_bytes, grantee_bytes, perm_bytes, salt_bytes]
    )

    try:
        is_active = adapter.is_permission_active(version_bytes, expected_hash)
        if is_active:
            grant.blockchain_status = "confirmed"
            db.commit()
    except Exception as e:
        logger.error(f"Error checking on-chain registry during sync_grant_blockchain_status: {str(e)}")


def verify_access_grant(user_id: uuid.UUID, version_id: uuid.UUID, required_permission: str, db: Session) -> bool:
    """
    Checks if a user has an active, valid grant for a specific version.
    Verifies the grant against on-chain permission commitments.
    Raises HTTPException for integrity/outage failures.
    """
    grant = db.query(DocumentAccessGrant).filter(
        DocumentAccessGrant.version_id == version_id,
        DocumentAccessGrant.granted_to_user_id == user_id,
        DocumentAccessGrant.revoked_at.is_(None)
    ).first()
    if not grant:
        return False
    
    if grant.expires_at is not None:
        utc_now = datetime.now(timezone.utc)
        if grant.expires_at <= utc_now:
            return False
            
    # Validate permission boundaries in DB lookup first
    db_perm_valid = False
    if required_permission == "DOWNLOAD":
        db_perm_valid = (grant.permission == "DOWNLOAD")
    elif required_permission == "VIEW":
        db_perm_valid = (grant.permission in ("VIEW", "DOWNLOAD"))

    if not db_perm_valid:
        # DB lookup fails permission boundary (e.g. required DOWNLOAD but DB is VIEW)
        # Rejects with standard permission failure before blockchain check is executed
        return False

    # Perform lazy synchronization of blockchain status for this grant
    sync_grant_blockchain_status(grant, db)

    # If the grant is not confirmed or has failed, deny access (no false CONFIRMED)
    if grant.blockchain_status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AUTHORIZATION_UNAVAILABLE: Grant blockchain commitment is not confirmed."
        )

    # Perform Blockchain Commitment Verification
    from web3 import Web3
    adapter = BlockchainAdapter()
    
    # Calculate the expected commitment hash using the exact database grant permission
    version_bytes = version_id.bytes
    grantee_bytes = user_id.bytes
    perm_bytes = grant.permission.encode('utf-8')
    salt_bytes = bytes.fromhex(grant.salt)

    expected_hash = Web3.solidity_keccak(
        ['bytes16', 'bytes16', 'bytes', 'bytes16'],
        [version_bytes, grantee_bytes, perm_bytes, salt_bytes]
    )

    try:
        is_active = adapter.is_permission_active(version_bytes, expected_hash)
    except Exception as e:
        logger.error(f"Blockchain RPC query failed during access check: {str(e)}")
        # CRITICAL: Do NOT fall back to PostgreSQL-only authorization on outage
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AUTHORIZATION_UNAVAILABLE: Blockchain ledger is unreachable."
        )

    if not is_active:
        log_audit_event(
            event_type="SECURITY_FAILURE",
            actor_user_id=user_id,
            case_id=None,
            document_id=grant.document_id,
            version_id=version_id,
            metadata={"reason": "unauthorized_database_grant_mismatch", "action": required_permission}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AUTHORIZATION_INTEGRITY_FAILURE"
        )

    return True


def get_active_grants_for_document(user_id: uuid.UUID, document_id: uuid.UUID, db: Session) -> list[DocumentAccessGrant]:
    """
    Retrieves all active (non-revoked, non-expired) grants for a user on any version of a document.
    """
    utc_now = datetime.now(timezone.utc)
    grants = db.query(DocumentAccessGrant).filter(
        DocumentAccessGrant.document_id == document_id,
        DocumentAccessGrant.granted_to_user_id == user_id,
        DocumentAccessGrant.revoked_at.is_(None)
    ).all()
    
    active = []
    for g in grants:
        if g.expires_at is None or g.expires_at > utc_now:
            active.append(g)
    return active


def check_document_access(
    document_id: uuid.UUID,
    version_id: Optional[uuid.UUID],
    required_permission: str,  # VIEW or DOWNLOAD
    current_user: User,
    db: Session
) -> tuple[Document, Optional[DocumentVersion]]:
    """
    Validates case participation (BOLA) and either Lead Lawyer status or active explicit grants.
    Raises HTTPException (404 for BOLA, 403 for permission failure).
    Logs ACCESS_DENIED on failure.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # 1. Enforce BOLA (Case participation)
    if not verify_case_participant(doc.case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # Determine target version
    target_ver = None
    if version_id:
        target_ver = db.query(DocumentVersion).filter(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == document_id
        ).first()
        if not target_ver:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    else:
        if doc.current_version_id:
            target_ver = db.query(DocumentVersion).filter(DocumentVersion.id == doc.current_version_id).first()

    # 2. Check Lead Lawyer bypass
    if is_lead_lawyer(doc.case_id, current_user.id, db):
        return doc, target_ver

    # 3. For general case participant: Check explicit version grants
    # If they have no active grants at all for this document, return 404 to hide its existence.
    active_grants = get_active_grants_for_document(current_user.id, document_id, db)
    if not active_grants:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if version_id is None:
        # Request for parent document passport. Check if they have access to current version.
        if target_ver and verify_access_grant(current_user.id, target_ver.id, required_permission, db):
            return doc, target_ver
        return doc, None

    # Request for a specific version.
    has_grant = verify_access_grant(current_user.id, target_ver.id, required_permission, db)
    if not has_grant:
        log_audit_event(
            event_type="ACCESS_DENIED",
            actor_user_id=current_user.id,
            case_id=doc.case_id,
            document_id=document_id,
            version_id=target_ver.id,
            metadata={"reason": "unauthorized_version_grant", "action": required_permission}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this document."
        )

    return doc, target_ver



def sync_blockchain_status(version: DocumentVersion, db: Session):
    """
    Reconciles the PostgreSQL blockchain state with the EVM ledger state.
    """
    if version.blockchain_status == "confirmed":
        return

    adapter = BlockchainAdapter()
    
    # 1. If transaction hash is known, check transaction status
    if version.blockchain_tx_hash:
        status_info = adapter.verify_transaction_status(version.blockchain_tx_hash)
        if status_info:
            version.blockchain_status = "confirmed"
            version.blockchain_block_number = status_info["block_number"]
            version.blockchain_timestamp = datetime.fromtimestamp(status_info["timestamp"], tz=timezone.utc)
            db.commit()
            return

    # 2. Check contract registry directly using version ID as the source of truth
    try:
        onchain_record = adapter.get_registration(version.id.bytes)
        if onchain_record:
            version.blockchain_status = "confirmed"
            version.blockchain_block_number = onchain_record["block_number"]
            version.blockchain_timestamp = datetime.fromtimestamp(onchain_record["timestamp"], tz=timezone.utc)
            db.commit()
    except Exception as e:
        logger.error(f"Error checking on-chain registry during sync: {str(e)}")

@router.get("/cases/{case_id}/documents", response_model=List[DocumentResponse])
def get_case_documents(
    case_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves all document records under a given case, enforcing BOLA case-participation
    and version-grant access parameters.
    """
    # 1. Enforce Case Participant authorization (BOLA)
    if not verify_case_participant(case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    # 2. Fetch all documents belonging to this case
    docs = db.query(Document).filter(Document.case_id == case_id).all()

    # 3. Lead Lawyer has absolute visibility
    if is_lead_lawyer(case_id, current_user.id, db):
        return docs

    # 4. General case participants can only see documents for which they have active version grants
    allowed_docs = []
    for doc in docs:
        active_grants = get_active_grants_for_document(current_user.id, doc.id, db)
        if active_grants:
            allowed_docs.append(doc)

    return allowed_docs

@router.post("/cases/{case_id}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    case_id: uuid.UUID,
    response: Response,
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: str = Form(...),
    x_idempotency_key: Optional[str] = Header(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Validates PDF, hashes, encrypts, saves to storage, commits to PostgreSQL as pending,
    then broadcasts to the blockchain registry, returning 201 Created.
    """
    # 1. Enforce Case Participant authorization
    if not verify_case_participant(case_id, current_user.id, db):
        logger.warning(
            f"Security Audit Failure: Unauthorized document upload attempt in Case {case_id} "
            f"by user {current_user.id} ({current_user.role})."
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    # 2. Extract and validate Idempotency Key
    idempotency_key = x_idempotency_key
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Idempotency-Key header."
        )

    # 3. Idempotency Check
    existing_doc = db.query(Document).filter(Document.idempotency_key == idempotency_key).first()
    if existing_doc:
        if existing_doc.owner_user_id == current_user.id and existing_doc.case_id == case_id:
            response.status_code = status.HTTP_200_OK
            return DocumentResponse.from_orm(existing_doc)
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key already exists with mismatched owner or case."
            )

    # 4. Strict File Validations
    max_size = 10 * 1024 * 1024
    content_bytes = await file.read()
    file_size = len(content_bytes)
    
    if file_size > max_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File size exceeds the 10MB limit.")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are supported.")

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file MIME type.")

    if len(content_bytes) < 5 or content_bytes[:5] != b"%PDF-":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed PDF magic bytes.")

    # 5. SHA-256 Fingerprinting
    sha256_hash = hashlib.sha256(content_bytes).hexdigest()

    # 6. Cryptographic Derivation and Encryption
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    
    version_key = KMSService.derive_version_key(str(doc_id), str(version_id))
    encrypted_bytes = encrypt_bytes(content_bytes, version_key)

    # 7. Upload to MinIO
    object_key = f"documents/{doc_id}/{version_id}"
    storage = StorageService()
    try:
        storage.put_object(object_key, encrypted_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage driver upload failed: {str(e)}"
        )

    # 8. Save to DB as 'pending'
    try:
        new_doc = Document(
            id=doc_id,
            case_id=case_id,
            title=title,
            document_type=document_type,
            owner_user_id=current_user.id,
            idempotency_key=idempotency_key
        )
        db.add(new_doc)
        
        new_version = DocumentVersion(
            id=version_id,
            document_id=doc_id,
            version_number=1,
            object_key=object_key,
            sha256_hash=sha256_hash,
            file_size=file_size,
            mime_type="application/pdf",
            created_by=current_user.id,
            blockchain_status="pending"
        )
        db.add(new_version)
        db.flush()

        new_doc.current_version_id = version_id
        db.commit()
        db.refresh(new_doc)
        db.refresh(new_version)
    except Exception as e:
        db.rollback()
        storage.delete_object(object_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database write failed. Storage cleaned up. Details: {str(e)}"
        )

    # 9. Register on Blockchain
    adapter = BlockchainAdapter()
    try:
        # Convert UUIDs to 16-byte raw format and SHA-256 to 32-byte bytes
        tx_hash = adapter.register_version(
            version_id.bytes,
            doc_id.bytes,
            bytes.fromhex(sha256_hash)
        )
        new_version.blockchain_status = "submitted"
        new_version.blockchain_tx_hash = tx_hash
        db.commit()
        db.refresh(new_version)
    except Exception as e:
        new_version.blockchain_status = "failed"
        db.commit()
        logger.error(f"Blockchain broadcast failed: {str(e)}")

    logger.info(f"Audit Event: DOCUMENT_CREATED - Document ID: {doc_id} - Version ID: {version_id} - Actor: {current_user.id}")
    return new_doc

@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
def get_document_details(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves document metadata details. Lazily syncs blockchain status if submitted.
    """
    doc, current_ver = check_document_access(document_id, None, "VIEW", current_user, db)

    if current_ver:
        sync_blockchain_status(current_ver, db)
    
    log_audit_event(
        event_type="DOCUMENT_VIEWED",
        actor_user_id=current_user.id,
        case_id=doc.case_id,
        document_id=doc.id,
        version_id=current_ver.id if current_ver else None
    )
    
    return DocumentDetailResponse(
        id=doc.id,
        case_id=doc.case_id,
        title=doc.title,
        document_type=doc.document_type,
        owner_user_id=doc.owner_user_id,
        current_version_id=current_ver.id if current_ver else None,
        classification=doc.classification,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        version_number=current_ver.version_number if current_ver else None,
        sha256_hash=current_ver.sha256_hash if current_ver else None,
        file_size=current_ver.file_size if current_ver else None,
        mime_type=current_ver.mime_type if current_ver else None,
        blockchain_status=current_ver.blockchain_status if current_ver else None,
        blockchain_tx_hash=current_ver.blockchain_tx_hash if current_ver else None,
        blockchain_block_number=current_ver.blockchain_block_number if current_ver else None,
        blockchain_timestamp=current_ver.blockchain_timestamp if current_ver else None
    )

@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersionResponse])
def get_document_versions(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves list of all document versions.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if not verify_case_participant(doc.case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if is_lead_lawyer(doc.case_id, current_user.id, db):
        allowed_versions = doc.versions
    else:
        active_grants = get_active_grants_for_document(current_user.id, document_id, db)
        allowed_version_ids = {g.version_id for g in active_grants}
        allowed_versions = [v for v in doc.versions if v.id in allowed_version_ids]
        if not allowed_versions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    for version in allowed_versions:
        sync_blockchain_status(version, db)

    log_audit_event(
        event_type="DOCUMENT_VIEWED",
        actor_user_id=current_user.id,
        case_id=doc.case_id,
        document_id=doc.id,
        metadata={"action": "list_versions"}
    )

    return allowed_versions

@router.get("/documents/{document_id}/download")
def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Downloads and decrypts document version.
    """
    doc, current_ver = check_document_access(document_id, None, "DOWNLOAD", current_user, db)
    if not current_ver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found.")

    storage = StorageService()
    try:
        encrypted_bytes = storage.get_object(current_ver.object_key)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage retrieval failed: {str(e)}"
        )

    version_key = KMSService.derive_version_key(str(document_id), str(current_ver.id))
    try:
        plaintext = decrypt_bytes(encrypted_bytes, version_key)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cryptographic decryption failure: unable to verify authenticity tag."
        )

    log_audit_event(
        event_type="DOCUMENT_DOWNLOADED",
        actor_user_id=current_user.id,
        case_id=doc.case_id,
        document_id=document_id,
        version_id=current_ver.id
    )

    return StreamingResponse(
        io.BytesIO(plaintext),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{doc.title}.pdf"'}
    )

@router.post("/documents/{document_id}/versions/{version_id}/register", status_code=status.HTTP_200_OK)
def retry_blockchain_registration(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually retries registration for a failed or pending document version.
    Only the Case Creator or Lead Lawyer is authorized.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # 1. Enforce Case Participant authorization (BOLA)
    if not verify_case_participant(doc.case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # 2. Restrict to Case Creator / Lead Lawyer
    creator_check = doc.created_by == current_user.id if hasattr(doc, "created_by") else doc.owner_user_id == current_user.id
    is_lead = creator_check or db.query(CaseParticipant).filter(
        CaseParticipant.case_id == doc.case_id,
        CaseParticipant.user_id == current_user.id,
        CaseParticipant.role == "lead_lawyer"
    ).first() is not None

    if not is_lead:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the case creator or lead lawyer can manage registration retry."
        )

    version = db.query(DocumentVersion).filter(
        DocumentVersion.id == version_id,
        DocumentVersion.document_id == document_id
    ).first()
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

    # Lazy check if already confirmed
    sync_blockchain_status(version, db)
    if version.blockchain_status == "confirmed":
        return {"status": "confirmed", "message": "Already registered on-chain."}

    adapter = BlockchainAdapter()
    
    # Check if contract already has this record (idempotency safety lookup)
    try:
        onchain_record = adapter.get_registration(version.id.bytes)
        if onchain_record:
            if onchain_record["document_id"] == doc.id.bytes:
                version.blockchain_status = "confirmed"
                version.blockchain_block_number = onchain_record["block_number"]
                version.blockchain_timestamp = datetime.fromtimestamp(onchain_record["timestamp"], tz=timezone.utc)
                db.commit()
                return {"status": "confirmed", "message": "Recovered registration from chain."}
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Version ID mapping already exists on-chain with a different Document ID."
                )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"Error querying chain during retry: {str(e)}")

    # Send transaction
    try:
        tx_hash = adapter.register_version(
            version.id.bytes,
            doc.id.bytes,
            bytes.fromhex(version.sha256_hash)
        )
        version.blockchain_status = "submitted"
        version.blockchain_tx_hash = tx_hash
        db.commit()
        return {"status": "submitted", "tx_hash": tx_hash}
    except Exception as e:
        version.blockchain_status = "failed"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Blockchain transaction broadcast failed: {str(e)}"
        )

@router.get("/documents/{document_id}/provenance")
def get_document_provenance(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns verifiable blockchain provenance records for the document's current version.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if not verify_case_participant(doc.case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    current_ver = db.query(DocumentVersion).filter(DocumentVersion.id == doc.current_version_id).first()
    if not current_ver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

    sync_blockchain_status(current_ver, db)
    adapter = BlockchainAdapter()

    return {
        "document_id": doc.id,
        "version_id": current_ver.id,
        "sha256_hash": current_ver.sha256_hash,
        "blockchain_status": current_ver.blockchain_status,
        "blockchain_tx_hash": current_ver.blockchain_tx_hash,
        "blockchain_block_number": current_ver.blockchain_block_number,
        "blockchain_timestamp": current_ver.blockchain_timestamp,
        "contract_address": adapter.contract_address,
        "registrar_address": adapter.registrar_address
    }

@router.post("/documents/{document_id}/versions", response_model=DocumentVersionResponse, status_code=status.HTTP_201_CREATED)
async def upload_document_version(
    document_id: uuid.UUID,
    response: Response,
    file: UploadFile = File(...),
    x_idempotency_key: Optional[str] = Header(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Creates a new version for an existing document.
    Enforces row locking, client-independent version numbers, PDF validation, KMS encryption, MinIO storage,
    DB immutability triggers, and blockchain registrations.
    """
    # 1. Fetch document and enforce participant authorization
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if not verify_case_participant(doc.case_id, current_user.id, db):
        logger.warning(
            f"Security Audit Failure: Unauthorized version creation attempt for Document {document_id} "
            f"by user {current_user.id} ({current_user.role})."
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # 2. Check and enforce Idempotency Key
    idempotency_key = x_idempotency_key
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Idempotency-Key header."
        )

    # Idempotent retry match lookup
    existing_ver = db.query(DocumentVersion).filter(DocumentVersion.idempotency_key == idempotency_key).first()
    if existing_ver:
        if existing_ver.created_by == current_user.id and existing_ver.document_id == document_id:
            response.status_code = status.HTTP_200_OK
            return existing_ver
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key already exists with mismatched owner or document."
            )

    # 3. File validations
    max_size = 10 * 1024 * 1024
    content_bytes = await file.read()
    file_size = len(content_bytes)

    if file_size > max_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File size exceeds the 10MB limit.")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are supported.")

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file MIME type.")

    if len(content_bytes) < 5 or content_bytes[:5] != b"%PDF-":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed PDF magic bytes.")

    # SHA-256 computation
    sha256_hash = hashlib.sha256(content_bytes).hexdigest()

    # 4. Pessimistic row locking on parent Document
    # Acquires a FOR UPDATE lock on the document row in PostgreSQL
    locked_doc = db.query(Document).filter(Document.id == document_id).with_for_update().first()
    if not locked_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # Determine latest version
    latest_ver = db.query(DocumentVersion).filter(
        DocumentVersion.document_id == document_id
    ).order_by(DocumentVersion.version_number.desc()).first()

    if not latest_ver:
        next_version_number = 1
        parent_version_id = None
    else:
        next_version_number = latest_ver.version_number + 1
        parent_version_id = latest_ver.id

    # 5. Encryption & KMS version key
    version_id = uuid.uuid4()
    version_key = KMSService.derive_version_key(str(document_id), str(version_id))
    encrypted_bytes = encrypt_bytes(content_bytes, version_key)

    # 6. Storage upload to MinIO
    object_key = f"documents/{document_id}/{version_id}"
    storage = StorageService()
    try:
        storage.put_object(object_key, encrypted_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage driver upload failed: {str(e)}"
        )

    # 7. Write PostgreSQL record
    try:
        new_version = DocumentVersion(
            id=version_id,
            document_id=document_id,
            version_number=next_version_number,
            object_key=object_key,
            sha256_hash=sha256_hash,
            file_size=file_size,
            mime_type="application/pdf",
            created_by=current_user.id,
            parent_version_id=parent_version_id,
            blockchain_status="pending",
            idempotency_key=idempotency_key
        )
        db.add(new_version)
        db.flush()
        locked_doc.current_version_id = version_id
        db.commit()
        db.refresh(new_version)
    except Exception as e:
        db.rollback()
        storage.delete_object(object_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database write failed. Storage cleaned up. Details: {str(e)}"
        )

    # 8. Blockchain Registration (reuses Adapter and fails gracefully to FAILED)
    adapter = BlockchainAdapter()
    try:
        tx_hash = adapter.register_version(
            version_id.bytes,
            document_id.bytes,
            bytes.fromhex(sha256_hash)
        )
        new_version.blockchain_status = "submitted"
        new_version.blockchain_tx_hash = tx_hash
        db.commit()
        db.refresh(new_version)
    except Exception as e:
        new_version.blockchain_status = "failed"
        db.commit()
        logger.error(f"Blockchain broadcast failed on version upload: {str(e)}")

    logger.info(f"Audit Event: DOCUMENT_VERSION_CREATED - Document ID: {document_id} - Version ID: {version_id} - Actor: {current_user.id}")
    return new_version

@router.get("/documents/{document_id}/versions/{version_id}", response_model=DocumentVersionResponse)
def get_document_version_metadata(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves metadata details for a specific version.
    """
    doc, version = check_document_access(document_id, version_id, "VIEW", current_user, db)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

    sync_blockchain_status(version, db)
    
    log_audit_event(
        event_type="DOCUMENT_VIEWED",
        actor_user_id=current_user.id,
        case_id=doc.case_id,
        document_id=document_id,
        version_id=version_id,
        metadata={"action": "view_version_metadata"}
    )
    return version

@router.get("/documents/{document_id}/versions/{version_id}/download")
def download_document_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Downloads and decrypts a specific document version.
    """
    doc, version = check_document_access(document_id, version_id, "DOWNLOAD", current_user, db)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

    storage = StorageService()
    try:
        encrypted_bytes = storage.get_object(version.object_key)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage retrieval failed: {str(e)}"
        )

    version_key = KMSService.derive_version_key(str(document_id), str(version_id))
    try:
        plaintext = decrypt_bytes(encrypted_bytes, version_key)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cryptographic decryption failure: unable to verify authenticity tag."
        )

    log_audit_event(
        event_type="DOCUMENT_DOWNLOADED",
        actor_user_id=current_user.id,
        case_id=doc.case_id,
        document_id=document_id,
        version_id=version_id
    )

    return StreamingResponse(
        io.BytesIO(plaintext),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{doc.title}_v{version.version_number}.pdf"'}
    )


@router.post("/documents/{document_id}/versions/{version_id}/access", response_model=DocumentAccessGrantResponse, status_code=status.HTTP_201_CREATED)
def grant_document_access(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    req: DocumentAccessGrantCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Grants a user access to a specific document version. Restricted to case lead lawyer.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if not verify_case_participant(doc.case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # Only case lead lawyer can grant access
    if not is_lead_lawyer(doc.case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the case lead lawyer can grant access.")

    # Verify version belongs to document
    version = db.query(DocumentVersion).filter(
        DocumentVersion.id == version_id,
        DocumentVersion.document_id == document_id
    ).first()
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

    # Grantee must be a case participant
    if not verify_case_participant(doc.case_id, req.user_id, db):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Grantee must be a case participant.")

    # Validate permission parameter
    if req.permission not in ("VIEW", "DOWNLOAD"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Permission must be VIEW or DOWNLOAD.")

    # Check for active (non-revoked) grant
    active_grant = db.query(DocumentAccessGrant).filter(
        DocumentAccessGrant.version_id == version_id,
        DocumentAccessGrant.granted_to_user_id == req.user_id,
        DocumentAccessGrant.revoked_at.is_(None)
    ).first()

    if active_grant:
        if active_grant.permission == req.permission:
            # Idempotent response
            return active_grant
        else:
            # Upgrade or downgrade permission: revoke old on-chain and in DB
            active_grant.revoked_at = datetime.now(timezone.utc)
            db.flush()
            
            try:
                from web3 import Web3
                old_version_bytes = version_id.bytes
                old_grantee_bytes = req.user_id.bytes
                old_perm_bytes = active_grant.permission.encode('utf-8')
                old_salt_bytes = bytes.fromhex(active_grant.salt)
                
                old_hash = Web3.solidity_keccak(
                    ['bytes16', 'bytes16', 'bytes', 'bytes16'],
                    [old_version_bytes, old_grantee_bytes, old_perm_bytes, old_salt_bytes]
                )
                adapter = BlockchainAdapter()
                adapter.revoke_permission(old_version_bytes, old_hash)
            except Exception as e:
                logger.error(f"Failed to revoke old permission on-chain during upgrade: {str(e)}")

            log_audit_event(
                event_type="ACCESS_REVOKED",
                actor_user_id=current_user.id,
                case_id=doc.case_id,
                document_id=document_id,
                version_id=version_id,
                metadata={"grant_id": str(active_grant.id), "reason": "upgrade_permission"}
            )

    # Create new grant
    new_grant = DocumentAccessGrant(
        document_id=document_id,
        version_id=version_id,
        granted_to_user_id=req.user_id,
        granted_by_user_id=current_user.id,
        permission=req.permission,
        expires_at=req.expires_at,
        blockchain_status="pending"
    )
    db.add(new_grant)
    db.commit()
    db.refresh(new_grant)

    # Register the new commitment on the blockchain
    try:
        from web3 import Web3
        version_bytes = version_id.bytes
        grantee_bytes = req.user_id.bytes
        perm_bytes = req.permission.encode('utf-8')
        salt_bytes = bytes.fromhex(new_grant.salt)
        
        commitment_hash = Web3.solidity_keccak(
            ['bytes16', 'bytes16', 'bytes', 'bytes16'],
            [version_bytes, grantee_bytes, perm_bytes, salt_bytes]
        )
        
        adapter = BlockchainAdapter()
        tx_hash = adapter.grant_permission(version_bytes, commitment_hash)
        new_grant.blockchain_status = "submitted"
        new_grant.blockchain_tx_hash = tx_hash
        db.commit()
        db.refresh(new_grant)
    except Exception as e:
        # If registration fails, preserve the grant in its failed/pending state and allow reconciliation to retry later
        new_grant.blockchain_status = "failed"
        db.commit()
        logger.error(f"Blockchain permission anchoring failed: {str(e)}")

    # Log access grant event AFTER successful transaction commit
    log_audit_event(
        event_type="ACCESS_GRANTED",
        actor_user_id=current_user.id,
        case_id=doc.case_id,
        document_id=document_id,
        version_id=version_id,
        metadata={"grant_id": str(new_grant.id), "permission": req.permission, "expires_at": str(req.expires_at) if req.expires_at else None}
    )

    return new_grant


@router.post("/documents/{document_id}/access/{grant_id}/revoke")
def revoke_document_access(
    document_id: uuid.UUID,
    grant_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Revokes access to a document version. Restricted to case lead lawyer.
    """
    grant = db.query(DocumentAccessGrant).filter(
        DocumentAccessGrant.id == grant_id,
        DocumentAccessGrant.document_id == document_id
    ).first()
    if not grant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access grant not found.")

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not verify_case_participant(doc.case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # Only case lead lawyer can revoke access
    if not is_lead_lawyer(doc.case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the case lead lawyer can revoke access.")

    if grant.revoked_at is None:
        grant.revoked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(grant)

        # Trigger on-chain revocation of this commitment
        try:
            from web3 import Web3
            version_bytes = grant.version_id.bytes
            grantee_bytes = grant.granted_to_user_id.bytes
            perm_bytes = grant.permission.encode('utf-8')
            salt_bytes = bytes.fromhex(grant.salt)
            
            commitment_hash = Web3.solidity_keccak(
                ['bytes16', 'bytes16', 'bytes', 'bytes16'],
                [version_bytes, grantee_bytes, perm_bytes, salt_bytes]
            )
            adapter = BlockchainAdapter()
            adapter.revoke_permission(version_bytes, commitment_hash)
        except Exception as e:
            logger.error(f"Blockchain revocation broadcast failed: {str(e)}")

        # Log access revocation AFTER successful transaction commit
        log_audit_event(
            event_type="ACCESS_REVOKED",
            actor_user_id=current_user.id,
            case_id=doc.case_id,
            document_id=document_id,
            version_id=grant.version_id,
            metadata={"grant_id": str(grant_id)}
        )

    return {"status": "success", "message": "Access grant revoked successfully."}


@router.get("/documents/{document_id}/access", response_model=List[DocumentAccessGrantResponse])
def list_document_access_grants(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Lists all access grants for a document. Restricted to case lead lawyer.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if not verify_case_participant(doc.case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # Only case lead lawyer can view all access grants
    if not is_lead_lawyer(doc.case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the case lead lawyer can view access grants.")

    grants = db.query(DocumentAccessGrant).filter(DocumentAccessGrant.document_id == document_id).all()
    return grants


@router.get("/documents/{document_id}/audit", response_model=List[AuditEventResponse])
def get_document_audit_timeline(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves the audit trail timeline for a document. Restricted to case lead lawyer.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if not verify_case_participant(doc.case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # Only case lead lawyer can view audit logs
    if not is_lead_lawyer(doc.case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the case lead lawyer can view audit logs.")

    events = db.query(AuditEvent).filter(
        AuditEvent.document_id == document_id
    ).order_by(AuditEvent.created_at.desc()).all()
    
    return events


@router.get("/documents/{document_id}/passport", response_model=DocumentPassportResponse)
def get_document_passport(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves the Document Passport containing case context, latest authorized version metadata,
    and allowed version history list. Restricted to case participants with at least one active grant
    or Lead Lawyer. Omit/redact unauthorized version details completely.
    """
    # 1. Fetch document
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # 2. BOLA check
    if not verify_case_participant(doc.case_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # 3. Determine authorized versions
    is_lead = is_lead_lawyer(doc.case_id, current_user.id, db)
    if is_lead:
        allowed_versions = doc.versions
    else:
        # Check active grants
        active_grants = get_active_grants_for_document(current_user.id, document_id, db)
        if not active_grants:
            # If no grants at all, hide document
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
        allowed_version_ids = {g.version_id for g in active_grants}
        allowed_versions = [v for v in doc.versions if v.id in allowed_version_ids]

    if not allowed_versions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # Synchronize blockchain status for allowed versions
    for v in allowed_versions:
        sync_blockchain_status(v, db)

    # 4. Determine latest authorized version details
    sorted_versions = sorted(allowed_versions, key=lambda x: x.version_number, reverse=True)
    latest_auth_ver = sorted_versions[0] if sorted_versions else None

    # Populate versions info list sorted asc (V1 -> V2 -> V3)
    versions_list = []
    for v in sorted(allowed_versions, key=lambda x: x.version_number):
        pub_url = f"{settings.public_verify_base_url}/verify/public/{v.opaque_verification_id}"
        versions_list.append(DocumentPassportVersionInfo(
            id=v.id,
            version_number=v.version_number,
            created_at=v.created_at,
            sha256_hash=v.sha256_hash,
            blockchain_status=v.blockchain_status,
            blockchain_tx_hash=v.blockchain_tx_hash,
            blockchain_block_number=v.blockchain_block_number,
            blockchain_timestamp=v.blockchain_timestamp,
            opaque_verification_id=v.opaque_verification_id,
            public_verification_url=pub_url
        ))

    from app.models.case import Case
    case = db.query(Case).filter(Case.id == doc.case_id).first()
    case_title = case.title if case else ""

    return DocumentPassportResponse(
        document_id=doc.id,
        case_id=doc.case_id,
        case_title=case_title,
        title=doc.title,
        document_type=doc.document_type,
        classification=doc.classification,
        owner_user_id=doc.owner_user_id,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        current_version_id=latest_auth_ver.id if latest_auth_ver else None,
        current_version_number=latest_auth_ver.version_number if latest_auth_ver else None,
        current_sha256_hash=latest_auth_ver.sha256_hash if latest_auth_ver else None,
        current_blockchain_status=latest_auth_ver.blockchain_status if latest_auth_ver else None,
        current_blockchain_tx_hash=latest_auth_ver.blockchain_tx_hash if latest_auth_ver else None,
        current_blockchain_timestamp=latest_auth_ver.blockchain_timestamp if latest_auth_ver else None,
        versions=versions_list
    )
