from __future__ import annotations

import base64
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .security import read_secret


class PiiCryptoError(RuntimeError):
    pass


def _key() -> bytes:
    encoded = read_secret("PII_ENCRYPTION_KEY")
    if not encoded:
        if os.getenv("ENVIRONMENT", "development").lower() == "production":
            raise PiiCryptoError("PII encryption key is required in production")
        return bytes(32)
    try:
        key = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, TypeError) as exc:
        raise PiiCryptoError("PII encryption key is invalid") from exc
    if len(key) != 32:
        raise PiiCryptoError("PII encryption key must decode to 32 bytes")
    return key


def encrypt_pii(value: str, *, tenant_id: str) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, value.encode(), tenant_id.encode())
    return "v1:" + base64.urlsafe_b64encode(nonce + ciphertext).decode().rstrip("=")


def decrypt_pii(value: str, *, tenant_id: str) -> str:
    if not value.startswith("v1:"):
        raise PiiCryptoError("PII ciphertext version is invalid")
    try:
        payload = base64.urlsafe_b64decode(value[3:] + "=" * (-len(value[3:]) % 4))
        return AESGCM(_key()).decrypt(payload[:12], payload[12:], tenant_id.encode()).decode()
    except Exception as exc:  # noqa: BLE001
        raise PiiCryptoError("PII ciphertext authentication failed") from exc
