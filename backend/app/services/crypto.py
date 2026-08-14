import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def encrypt_bytes(plaintext: bytes, key: bytes) -> bytes:
    """
    Encrypts plaintext bytes using AES-256-GCM.
    Payload Format: nonce (12 bytes) + tag (16 bytes) + ciphertext
    """
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    # AESGCM.encrypt returns ciphertext with tag appended at the end (16 bytes)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext, None)
    
    # Extract tag and ciphertext to structure payload as: nonce + tag + ciphertext
    tag = ciphertext_with_tag[-16:]
    ciphertext = ciphertext_with_tag[:-16]
    
    return nonce + tag + ciphertext

def decrypt_bytes(payload: bytes, key: bytes) -> bytes:
    """
    Decrypts AES-256-GCM encrypted payload.
    Payload Format: nonce (12 bytes) + tag (16 bytes) + ciphertext
    """
    if len(payload) < 28:
        raise ValueError("Malformed encrypted payload: insufficient bytes.")

    nonce = payload[:12]
    tag = payload[12:28]
    ciphertext = payload[28:]
    
    aesgcm = AESGCM(key)
    # Re-append tag for python cryptography library compatibility
    ciphertext_with_tag = ciphertext + tag
    return aesgcm.decrypt(nonce, ciphertext_with_tag, None)
