import os

import pytest

from course_mcp_server.billing import process_checkout_event
from course_mcp_server.billing_repository import (
    customer_id_for_tenant,
    reconcile,
    upsert_subscription,
)
from course_mcp_server.database import database_url
from scripts.apply_migrations import apply


pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration only")


def test_checkout_subscription_lifecycle_and_reconciliation(tmp_path, monkeypatch):
    apply(database_url())
    monkeypatch.setenv("LICENSE_STORE_PATH", str(tmp_path / "licenses.json"))
    monkeypatch.setenv("LICENSE_DELIVERY_MODE", "return")
    checkout = {
        "id": "evt_checkout_pg",
        "created": 100,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_pg",
                "customer": "cus_pg",
                "subscription": "sub_provider_pg",
                "metadata": {"tenant": "tenant-billing", "tier": "pro"},
            }
        },
    }
    first = process_checkout_event(checkout)
    assert first["processed"] is True
    assert customer_id_for_tenant("tenant-billing") == "cus_pg"
    with pytest.raises(LookupError):
        customer_id_for_tenant("tenant-billing-attacker")
    assert process_checkout_event(checkout)["duplicate"] is True

    failed = {
        "id": "evt_failed_pg",
        "created": 101,
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "subscription": "sub_provider_pg",
                "customer": "cus_pg",
                "metadata": {"tenant": "tenant-billing", "tier": "pro"},
            }
        },
    }
    assert process_checkout_event(failed)["subscription_status"] == "past_due"
    restored = {
        **failed,
        "id": "evt_restored_pg",
        "created": 102,
        "type": "invoice.payment_succeeded",
    }
    assert process_checkout_event(restored)["entitlement_active"] is True
    stale = {**failed, "id": "evt_stale_pg", "created": 99}
    stale_result = process_checkout_event(stale)
    assert stale_result["stale_event"] is True
    assert stale_result["subscription_status"] == "active"
    assert stale_result["entitlement_active"] is True
    report = reconcile()
    assert report["unexplained_differences"] == 0


def test_provider_subscription_cannot_cross_tenant_boundary():
    apply(database_url())
    provider_id = "sub_cross_tenant_boundary"
    upsert_subscription(
        tenant_id="tenant-billing-owner",
        provider_subscription_id=provider_id,
        customer_id="cus_owner",
        tier="pro",
        status="active",
    )
    with pytest.raises(PermissionError, match="another tenant"):
        upsert_subscription(
            tenant_id="tenant-billing-attacker",
            provider_subscription_id=provider_id,
            customer_id="cus_attacker",
            tier="enterprise",
            status="active",
        )
