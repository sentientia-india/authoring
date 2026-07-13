import hashlib
import hmac
import json
import time

import pytest

from course_mcp_server.billing import BillingError, handle_stripe_webhook
from course_mcp_server.licensing import resolve_license
from course_mcp_server.provenance import sign_export, verify_export_stamp


def _stripe_signature(payload: bytes, secret: str, timestamp: int) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def test_checkout_webhook_provisions_license_idempotently(tmp_path, monkeypatch):
    monkeypatch.setattr("course_mcp_server.licensing.database_url", lambda: None)
    monkeypatch.setattr("course_mcp_server.billing.database_url", lambda: None)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("LICENSE_STORE_PATH", str(tmp_path / "licenses.json"))
    monkeypatch.setenv("BILLING_EVENT_STORE_PATH", str(tmp_path / "billing.json"))
    monkeypatch.setenv("LICENSE_DELIVERY_MODE", "return")
    event = {
        "id": "evt_123",
        "type": "checkout.session.completed",
        "data": {"object": {"customer": "cus_123", "metadata": {"tenant": "acme", "tier": "pro"}}},
    }
    payload = json.dumps(event).encode()
    signature = _stripe_signature(payload, "whsec_test", int(time.time()))

    first = handle_stripe_webhook(payload, signature)
    assert first["processed"] is True
    assert resolve_license(first["license_key"]).tenant == "acme"
    second = handle_stripe_webhook(payload, signature)
    assert second["duplicate"] is True
    assert "license_key" not in second


def test_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    with pytest.raises(BillingError):
        handle_stripe_webhook(b"{}", f"t={int(time.time())},v1=bad")


def test_export_stamp_detects_tampering(monkeypatch):
    monkeypatch.setenv("EXPORT_SIGNING_SECRET", "signing-secret")
    stamp = sign_export("course_123", "acme", "pro")
    assert verify_export_stamp(stamp)
    stamp["tenant"] = "attacker"
    assert not verify_export_stamp(stamp)
