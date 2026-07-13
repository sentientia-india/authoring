from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

from .database import connection, ensure_tenant


def previous_event(provider_event_id: str) -> dict[str, Any] | None:
    with connection() as active:
        row = active.execute(
            "SELECT processing_result FROM billing_events WHERE provider = 'stripe' AND provider_event_id = %s",
            (provider_event_id,),
        ).fetchone()
    return dict(row["processing_result"]) if row else None


def record_event(event: dict[str, Any], result: dict[str, Any], tenant_id: str | None) -> None:
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
    with connection() as active:
        active.execute(
            """
            INSERT INTO billing_events
                (provider, provider_event_id, event_type, payload_sha256, tenant_id, processing_result)
            VALUES ('stripe', %s, %s, %s, %s, %s)
            ON CONFLICT (provider, provider_event_id) DO NOTHING
            """,
            (
                event["id"],
                event.get("type", "unknown"),
                hashlib.sha256(canonical).hexdigest(),
                tenant_id,
                Jsonb(result),
            ),
        )


def upsert_subscription(
    *,
    tenant_id: str,
    provider_subscription_id: str,
    customer_id: str | None,
    tier: str,
    status: str,
    product_id: str | None = None,
    price_id: str | None = None,
    snapshot_version: int = 0,
) -> dict[str, Any]:
    subscription_id = f"sub_{hashlib.sha256(f'stripe:{provider_subscription_id}'.encode()).hexdigest()[:24]}"
    with connection() as active:
        ensure_tenant(active, tenant_id)
        row = active.execute(
            """
            INSERT INTO subscriptions
                (tenant_id, subscription_id, provider, provider_subscription_id,
                 provider_customer_id, product_id, price_id, tier, status, provider_snapshot_version)
            VALUES (%s, %s, 'stripe', %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider, provider_subscription_id) DO UPDATE
            SET status = EXCLUDED.status, tier = EXCLUDED.tier,
                provider_customer_id = EXCLUDED.provider_customer_id,
                product_id = EXCLUDED.product_id, price_id = EXCLUDED.price_id,
                provider_snapshot_version = GREATEST(subscriptions.provider_snapshot_version, EXCLUDED.provider_snapshot_version),
                updated_at = now()
            WHERE subscriptions.tenant_id = EXCLUDED.tenant_id
              AND EXCLUDED.provider_snapshot_version >= subscriptions.provider_snapshot_version
            RETURNING tenant_id, subscription_id, tier, status, provider_subscription_id
            """,
            (
                tenant_id,
                subscription_id,
                provider_subscription_id,
                customer_id,
                product_id,
                price_id,
                tier,
                status,
                snapshot_version,
            ),
        ).fetchone()
        if row:
            return {**dict(row), "applied": True}
        existing = active.execute(
            """
            SELECT tenant_id, subscription_id, tier, status, provider_subscription_id
            FROM subscriptions WHERE provider = 'stripe' AND provider_subscription_id = %s
            """,
            (provider_subscription_id,),
        ).fetchone()
        if not existing or existing["tenant_id"] != tenant_id:
            raise PermissionError("Subscription belongs to another tenant")
    return {**dict(existing), "applied": False}


def set_plan_entitlement(*, tenant_id: str, subscription_id: str, tier: str, active: bool) -> None:
    entitlement_id = f"ent_{hashlib.sha256(f'{tenant_id}:{subscription_id}:plan'.encode()).hexdigest()[:24]}"
    status = "active" if active else "suspended"
    with connection() as active_connection:
        active_connection.execute(
            """
            INSERT INTO entitlements
                (tenant_id, entitlement_id, capability, source_type, source_id, status)
            VALUES (%s, %s, %s, 'subscription', %s, %s)
            ON CONFLICT (tenant_id, capability, source_type, source_id) DO UPDATE
            SET status = EXCLUDED.status,
                revoked_at = CASE WHEN EXCLUDED.status = 'active' THEN NULL ELSE now() END
            """,
            (tenant_id, entitlement_id, f"plan:{tier}", subscription_id, status),
        )


def reconcile() -> dict[str, Any]:
    run_id = f"recon_{int(datetime.now(timezone.utc).timestamp())}"
    with connection() as active:
        row = active.execute(
            """
            WITH counts AS (
                SELECT
                    (SELECT count(*) FROM subscriptions WHERE status IN ('trialing', 'active')) AS subscriptions,
                    (SELECT count(*) FROM entitlements WHERE status = 'active' AND source_type = 'subscription') AS entitlements
            )
            INSERT INTO reconciliation_runs
                (run_id, provider, completed_at, subscription_count, entitlement_count, unexplained_differences, result)
            SELECT %s, 'stripe', now(), subscriptions, entitlements,
                   abs(subscriptions - entitlements),
                   jsonb_build_object('subscriptions', subscriptions, 'entitlements', entitlements)
            FROM counts
            RETURNING run_id, subscription_count, entitlement_count, unexplained_differences
            """,
            (run_id,),
        ).fetchone()
    return dict(row)
