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
from pathlib import Path
from typing import Any
from email.message import EmailMessage

from .licensing import issue_license


class BillingError(RuntimeError):
    pass


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
    events = _load_events()
    if event_id in events["processed"]:
        return {"processed": False, "duplicate": True, **events["processed"][event_id]}
    if event.get("type") != "checkout.session.completed":
        return {"processed": False, "ignored": True}

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
    events["processed"][event_id] = receipt
    _save_events(events)
    return {"processed": True, "duplicate": False, "license_key": license_key, **receipt}


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
