import json

import pytest

from course_mcp_server.billing import BillingError, create_checkout_session, create_customer_portal_session


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_checkout_and_portal_sessions_use_server_side_stripe_api(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        if request.full_url.endswith("checkout/sessions"):
            return Response({"id": "cs_test_1", "url": "https://checkout.stripe.com/test"})
        return Response({"id": "bps_1", "url": "https://billing.stripe.com/test"})

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_secret")
    monkeypatch.setenv(
        "STRIPE_PRICE_CATALOG", '{"price_123":{"tier":"pro","mode":"subscription"}}'
    )
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("course_mcp_server.billing.database_url", lambda: "postgresql://configured")
    monkeypatch.setattr("course_mcp_server.billing.customer_id_for_tenant", lambda tenant: "cus_123")
    checkout = create_checkout_session(
        tenant_id="tenant-a",
        price_id="price_123",
        tier="pro",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
        share_token="share-token",
    )
    portal = create_customer_portal_session(tenant_id="tenant-a", return_url="https://example.com/account")
    assert checkout["checkout_session_id"] == "cs_test_1"
    assert portal["portal_session_id"] == "bps_1"
    assert all(timeout == 20 for _, timeout in requests)
    assert all("sk_test_secret" not in request.full_url for request, _ in requests)


def test_checkout_rejects_untrusted_return_urls(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_secret")
    monkeypatch.setenv(
        "STRIPE_PRICE_CATALOG", '{"price_123":{"tier":"pro","mode":"subscription"}}'
    )
    with pytest.raises(BillingError):
        create_checkout_session(
            tenant_id="tenant-a",
            price_id="price_123",
            tier="pro",
            success_url="http://insecure.example/success",
            cancel_url="https://example.com/cancel",
        )


def test_checkout_rejects_client_tier_escalation(monkeypatch):
    monkeypatch.setenv(
        "STRIPE_PRICE_CATALOG", '{"price_cheap":{"tier":"free","mode":"subscription"}}'
    )
    with pytest.raises(BillingError, match="does not match price"):
        create_checkout_session(
            tenant_id="tenant-a",
            price_id="price_cheap",
            tier="white_label",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )


def test_portal_uses_customer_owned_by_authenticated_tenant(monkeypatch):
    monkeypatch.setattr("course_mcp_server.billing.database_url", lambda: "postgresql://configured")
    monkeypatch.setattr(
        "course_mcp_server.billing.customer_id_for_tenant",
        lambda tenant: (_ for _ in ()).throw(LookupError()) if tenant == "attacker" else "cus_owned",
    )
    with pytest.raises(BillingError, match="unavailable"):
        create_customer_portal_session(
            tenant_id="attacker", return_url="https://example.com/account"
        )
