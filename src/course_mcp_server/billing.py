"""Stripe webhook verification and license lifecycle provisioning.

This module is transport-neutral so webhook handling can be tested without
network access. It never logs webhook bodies, API keys, or generated licenses.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import smtplib
import time
import base64
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from email.message import EmailMessage

from .licensing import issue_license
from .database import database_url
from .billing_repository import previous_event, record_event, set_plan_entitlement, upsert_subscription
from .hosted_learning import grant_paid_access
from .communication import queue_email


class BillingError(RuntimeError):
    pass


def _stripe_post(path: str, fields: dict[str, Any]) -> dict[str, Any]:
    secret = os.getenv("STRIPE_SECRET_KEY", "")
    if not secret.startswith("sk_"):
        raise BillingError("Stripe secret key is not configured")
    encoded = urllib.parse.urlencode({key: value for key, value in fields.items() if value is not None}).encode()
    authorization = base64.b64encode(f"{secret}:".encode()).decode()
    request = urllib.request.Request(
        f"https://api.stripe.com/v1/{path.lstrip('/')}",
        data=encoded,
        headers={
            "Authorization": f"Basic {authorization}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise BillingError("Stripe API request failed") from exc
    if not isinstance(result, dict) or not result.get("id"):
        raise BillingError("Stripe API returned an invalid response")
    return result


def create_checkout_session(
    *,
    tenant_id: str,
    price_id: str,
    tier: str,
    success_url: str,
    cancel_url: str,
    share_token: str | None = None,
    mode: str = "subscription",
) -> dict[str, Any]:
    if mode not in {"subscription", "payment"} or not price_id.startswith("price_"):
        raise BillingError("Invalid checkout configuration")
    if not success_url.startswith("https://") or not cancel_url.startswith("https://"):
        raise BillingError("Checkout return URLs must use HTTPS")
    session = _stripe_post(
        "checkout/sessions",
        {
            "mode": mode,
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": 1,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": tenant_id,
            "metadata[tenant]": tenant_id,
            "metadata[tier]": tier,
            "metadata[share_token]": share_token,
        },
    )
    return {"checkout_session_id": session["id"], "checkout_url": session.get("url")}


def create_customer_portal_session(*, customer_id: str, return_url: str) -> dict[str, Any]:
    if not customer_id.startswith("cus_") or not return_url.startswith("https://"):
        raise BillingError("Invalid customer portal configuration")
    session = _stripe_post("billing_portal/sessions", {"customer": customer_id, "return_url": return_url})
    return {"portal_session_id": session["id"], "portal_url": session.get("url")}


def verify_stripe_signature(payload: bytes, signature: str, secret: str, tolerance: int = 300) -> None:
    fields = dict(item.split("=", 1) for item in signature.split(",") if "=" in item)
    timestamp = int(fields.get("t", "0"))
    if abs(int(time.time()) - timestamp) > tolerance:
        raise BillingError("Stripe signature timestamp is outside the allowed window")
    signed = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, fields.get("v1", "")):
        raise BillingError("Invalid Stripe webhook signature")


def _event_store_path() -> Path:
    output = Path(os.getenv("OUTPUT_DIR", "course_mcp_output"))
    return Path(os.getenv("BILLING_EVENT_STORE_PATH", str(output / "billing_events.json")))


def _load_events() -> dict[str, Any]:
    path = _event_store_path()
    if not path.exists():
        return {"processed": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"processed": {}}


def _save_events(events: dict[str, Any]) -> None:
    path = _event_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(events, indent=2), encoding="utf-8")


def process_checkout_event(event: dict[str, Any]) -> dict[str, Any]:
    event_id = str(event.get("id") or "")
    if not event_id:
        raise BillingError("Stripe event has no id")
    if database_url():
        previous = previous_event(event_id)
        if previous:
            return {"processed": False, "duplicate": True, **previous}
    else:
        events = _load_events()
        if event_id in events["processed"]:
            return {"processed": False, "duplicate": True, **events["processed"][event_id]}
    event_type = str(event.get("type") or "")
    if event_type != "checkout.session.completed":
        return _process_subscription_event(event)

    session = event.get("data", {}).get("object", {})
    metadata = session.get("metadata") or {}
    tenant = str(metadata.get("tenant") or session.get("customer") or "").strip()
    tier = str(metadata.get("tier") or "pro")
    if not tenant:
        raise BillingError("Checkout session has no tenant/customer identity")
    license_key = "smr_" + secrets.token_urlsafe(32)
    issue_license(license_key, tenant=tenant, tier=tier)
    email = str((session.get("customer_details") or {}).get("email") or metadata.get("email") or "")
    delivery_mode = os.getenv("LICENSE_DELIVERY_MODE", "smtp")
    if delivery_mode == "smtp":
        _deliver_license_email(email, tenant, tier, license_key)
    elif delivery_mode != "return":
        raise BillingError("Unsupported license delivery mode")
    receipt = {
        "tenant": tenant,
        "tier": tier,
        "customer": session.get("customer"),
        "created": int(time.time()),
        "delivered": delivery_mode == "smtp",
    }
    subscription_id = str(session.get("subscription") or f"checkout:{session.get('id') or event_id}")
    if database_url():
        subscription = upsert_subscription(
            tenant_id=tenant,
            provider_subscription_id=subscription_id,
            customer_id=session.get("customer"),
            tier=tier,
            status="active",
            price_id=metadata.get("price_id"),
            product_id=metadata.get("product_id"),
            snapshot_version=int(event.get("created") or 0),
        )
        set_plan_entitlement(
            tenant_id=tenant, subscription_id=subscription["subscription_id"], tier=tier, active=True
        )
        share_token = str(metadata.get("share_token") or "")
        if share_token and email:
            access = grant_paid_access(share_token, email)
            receipt["hosted_access_provisioned"] = True
            receipt["access_token"] = access["access_token"]
        if email:
            queue_email(
                tenant_id=tenant,
                recipient=email,
                template="receipt",
                data={
                    "product_name": str(metadata.get("product_name") or f"{tier} subscription"),
                    "amount": str(session.get("amount_total") or "paid"),
                    "action_url": str(metadata.get("receipt_url") or metadata.get("account_url") or "https://example.invalid/account"),
                },
                idempotency_key=f"receipt:{event_id}",
            )
        record_event(event, receipt, tenant)
    else:
        events["processed"][event_id] = receipt
        _save_events(events)
    return {"processed": True, "duplicate": False, "license_key": license_key, **receipt}


def _process_subscription_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("type") or "")
    supported = {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_succeeded",
        "invoice.payment_failed",
        "charge.refunded",
        "charge.dispute.created",
    }
    if event_type not in supported:
        result = {"processed": False, "ignored": True, "event_type": event_type}
        if database_url():
            record_event(event, result, None)
        return result
    obj = event.get("data", {}).get("object", {})
    metadata = obj.get("metadata") or {}
    tenant = str(metadata.get("tenant") or "").strip()
    provider_subscription_id = str(obj.get("subscription") or obj.get("id") or "")
    if not tenant or not provider_subscription_id:
        result = {"processed": False, "ignored": True, "event_type": event_type, "reason": "missing_identity"}
        if database_url():
            record_event(event, result, tenant or None)
        return result
    tier = str(metadata.get("tier") or "pro")
    status = str(obj.get("status") or "active")
    if event_type == "customer.subscription.deleted":
        status = "canceled"
    elif event_type == "invoice.payment_failed":
        status = "past_due"
    elif event_type == "invoice.payment_succeeded":
        status = "active"
    elif event_type == "charge.refunded":
        status = "refunded"
    elif event_type == "charge.dispute.created":
        status = "disputed"
    allowed = {"trialing", "active", "past_due", "paused", "canceled", "refunded", "disputed"}
    status = status if status in allowed else "past_due"
    if not database_url():
        return {"processed": False, "ignored": True, "event_type": event_type}
    subscription = upsert_subscription(
        tenant_id=tenant,
        provider_subscription_id=provider_subscription_id,
        customer_id=obj.get("customer"),
        tier=tier,
        status=status,
        snapshot_version=int(event.get("created") or 0),
    )
    active = status in {"trialing", "active"}
    set_plan_entitlement(
        tenant_id=tenant,
        subscription_id=subscription["subscription_id"],
        tier=tier,
        active=active,
    )
    result = {
        "processed": True,
        "duplicate": False,
        "tenant": tenant,
        "tier": tier,
        "subscription_status": status,
        "entitlement_active": active,
    }
    email = str(obj.get("customer_email") or metadata.get("email") or "")
    if event_type == "invoice.payment_failed" and email:
        queue_email(
            tenant_id=tenant,
            recipient=email,
            template="dunning",
            data={"action_url": str(metadata.get("account_url") or "https://example.invalid/account")},
            idempotency_key=f"dunning:{event['id']}",
        )
    record_event(event, result, tenant)
    return result


def _deliver_license_email(email: str, tenant: str, tier: str, license_key: str) -> None:
    host = os.getenv("SMTP_HOST", "")
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("LICENSE_FROM_EMAIL", username)
    if not email or not host or not sender:
        raise BillingError("SMTP license delivery is not configured")
    message = EmailMessage()
    message["Subject"] = "Your Samrat Course MCP license"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        f"Your {tier} license for {tenant} is:\n\n{license_key}\n\nKeep this key private."
    )
    try:
        with smtplib.SMTP_SSL(host, int(os.getenv("SMTP_PORT", "465")), timeout=20) as smtp:
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
    except Exception as exc:  # noqa: BLE001
        raise BillingError("License delivery failed") from exc


def handle_stripe_webhook(payload: bytes, signature: str) -> dict[str, Any]:
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise BillingError("Stripe webhook secret is not configured")
    verify_stripe_signature(payload, signature, secret)
    return process_checkout_event(json.loads(payload.decode("utf-8")))
