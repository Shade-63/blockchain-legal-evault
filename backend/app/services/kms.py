import base64
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from app.config import settings

class KMSService:
    """
    Isolated Key Management Service (KMS) abstraction.
    Derives unique keys per document version using HKDF-SHA256 from the master key.
    Can be replaced in production by a hardware KMS/HSM.
    """
    @staticmethod
    def derive_version_key(document_id: str, version_id: str) -> bytes:
        """
        Derives a unique 32-byte key for a specific document version.
        HKDF-SHA256(master_key, info="legal-evault/document/{document_id}/version/{version_id}")
        """
        master_key_str = settings.jwt_secret
        master_bytes = master_key_str.encode("utf-8")

        # Contextual info binding document ID and version ID
        info = f"legal-evault/document/{document_id}/version/{version_id}".encode("utf-8")

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=info
        )
        return hkdf.derive(master_bytes)
