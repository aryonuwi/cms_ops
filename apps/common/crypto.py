"""Symmetric encryption primitives with dynamic per-user key derivation.

Used for sensitive secrets such as TOTP seeds. Secrets are encrypted using
Fernet (AES-128-CBC + HMAC-SHA256), keyed with a per-user derived key via
HKDF-SHA256. Any manual alteration or database tampering renders the token
invalid and raises TamperDetectedError.
"""

from __future__ import annotations

import base64
import uuid

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings


class TamperDetectedError(Exception):
    """Raised when decrypting a secret fails due to corruption or tampering."""


def _get_master_key_bytes() -> bytes:
    raw_key = getattr(settings, "TWO_FACTOR_ENCRYPTION_KEY", "")
    if not raw_key:
        raise ValueError("TWO_FACTOR_ENCRYPTION_KEY is not configured.")
    # If the key is urlsafe base64 encoded, decode it to raw bytes, else use as utf-8 bytes
    try:
        decoded = base64.urlsafe_b64decode(raw_key.encode("utf-8"))
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    return raw_key.encode("utf-8")


def derive_user_key(*, user_id: uuid.UUID, context: str = "") -> bytes:
    """Derive a distinct 32-byte Fernet key for a specific user and context.

    Uses HKDF-SHA256 with user_id.bytes as salt and context as info.
    """
    master_bytes = _get_master_key_bytes()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=user_id.bytes,
        info=f"ops_views:2fa:{context}".encode("utf-8"),
    )
    derived_32 = hkdf.derive(master_bytes)
    return base64.urlsafe_b64encode(derived_32)


def encrypt_user_secret(
    *, plaintext: str, user_id: uuid.UUID, context: str = ""
) -> bytes:
    """Encrypt a secret string for a specific user.

    Returns the ciphertext bytes suitable for storing in a BinaryField.
    """
    fernet_key = derive_user_key(user_id=user_id, context=context)
    fernet = Fernet(fernet_key)
    return fernet.encrypt(plaintext.encode("utf-8"))


def decrypt_user_secret(
    *, ciphertext: bytes, user_id: uuid.UUID, context: str = ""
) -> str:
    """Decrypt a secret ciphertext for a specific user.

    Raises TamperDetectedError if decryption fails (e.g. wrong user, corrupted
    ciphertext, or manual DB modification).
    """
    if not ciphertext:
        raise TamperDetectedError("Empty ciphertext provided.")

    fernet_key = derive_user_key(user_id=user_id, context=context)
    fernet = Fernet(fernet_key)
    try:
        decrypted = fernet.decrypt(ciphertext)
        return decrypted.decode("utf-8")
    except (InvalidToken, Exception) as exc:
        raise TamperDetectedError(
            f"Failed to decrypt secret for user {user_id}: token is invalid or tampered."
        ) from exc
