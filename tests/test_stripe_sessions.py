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
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    checkout = create_checkout_session(
        tenant_id="tenant-a",
        price_id="price_123",
        tier="pro",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
        share_token="share-token",
    )
    portal = create_customer_portal_session(customer_id="cus_123", return_url="https://example.com/account")
    assert checkout["checkout_session_id"] == "cs_test_1"
    assert portal["portal_session_id"] == "bps_1"
    assert all(timeout == 20 for _, timeout in requests)
    assert all("sk_test_secret" not in request.full_url for request, _ in requests)


def test_checkout_rejects_untrusted_return_urls(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_secret")
    with pytest.raises(BillingError):
        create_checkout_session(
            tenant_id="tenant-a",
            price_id="price_123",
            tier="pro",
            success_url="http://insecure.example/success",
            cancel_url="https://example.com/cancel",
        )
