import base64

import pytest

from course_mcp_server.pii_crypto import PiiCryptoError, decrypt_pii, encrypt_pii


def test_pii_ciphertext_is_authenticated_and_tenant_bound(monkeypatch):
    monkeypatch.setenv("PII_ENCRYPTION_KEY", base64.urlsafe_b64encode(bytes(range(32))).decode())
    encrypted = encrypt_pii("learner@example.com", tenant_id="tenant-a")
    assert encrypted.startswith("v1:")
    assert "learner@example.com" not in encrypted
    assert decrypt_pii(encrypted, tenant_id="tenant-a") == "learner@example.com"
    with pytest.raises(PiiCryptoError, match="authentication failed"):
        decrypt_pii(encrypted, tenant_id="tenant-b")
