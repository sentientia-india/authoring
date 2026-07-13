from __future__ import annotations

import hashlib
import json
import os
import re
import smtplib
from email.message import EmailMessage
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from .database import connection, ensure_tenant
from .pii_crypto import decrypt_pii, encrypt_pii


class CommunicationError(RuntimeError):
    pass


TEMPLATES = {
    "invitation": ("You are invited to {course_title}", "Open your course: {action_url}"),
    "receipt": ("Your receipt for {product_name}", "Payment received: {amount}. Receipt: {action_url}"),
    "enrollment": ("You are enrolled in {course_title}", "Start learning: {action_url}"),
    "completion": ("You completed {course_title}", "Congratulations. Certificate: {action_url}"),
    "dunning": ("Payment action required", "Update your payment method: {action_url}"),
    "report": ("Your {report_type} learning report", "Download the report: {action_url}"),
}


def _email_hash(email: str) -> str:
    normalized = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise CommunicationError("Invalid email")
    return hashlib.sha256(normalized.encode()).hexdigest()


def render_template(template: str, data: dict[str, Any]) -> tuple[str, str]:
    if template not in TEMPLATES:
        raise CommunicationError("Unsupported email template")
    try:
        subject = TEMPLATES[template][0].format_map(data)
        body = TEMPLATES[template][1].format_map(data)
    except KeyError as exc:
        raise CommunicationError("Missing email template data") from exc
    return subject, body


def queue_email(
    *, tenant_id: str, recipient: str, template: str, data: dict[str, Any], idempotency_key: str
) -> dict[str, Any]:
    render_template(template, data)
    recipient_hash = _email_hash(recipient)
    delivery_id = f"mail_{hashlib.sha256(f'{tenant_id}:{idempotency_key}'.encode()).hexdigest()[:24]}"
    event_id = f"evt_{uuid4().hex}"
    with connection() as active:
        ensure_tenant(active, tenant_id)
        suppressed = active.execute(
            "SELECT 1 FROM email_suppressions WHERE email_hash = %s", (recipient_hash,)
        ).fetchone()
        status = "suppressed" if suppressed else "queued"
        active.execute(
            """
            INSERT INTO email_deliveries
                (tenant_id, delivery_id, template, recipient_hash, recipient_ciphertext,
                 template_data, template_data_ciphertext, idempotency_key, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            """,
            (
                tenant_id,
                delivery_id,
                template,
                recipient_hash,
                encrypt_pii(recipient.strip().lower(), tenant_id=tenant_id),
                Jsonb({"encrypted": True}),
                encrypt_pii(json.dumps(data, sort_keys=True), tenant_id=tenant_id),
                idempotency_key,
                status,
            ),
        )
        if status == "queued":
            active.execute(
                """
                INSERT INTO outbox_events
                    (tenant_id, event_id, event_type, event_version, aggregate_type,
                     aggregate_id, sequence, idempotency_key, payload)
                VALUES (%s, %s, 'email.queued', 1, 'email_delivery', %s, 1, %s, %s)
                ON CONFLICT (tenant_id, event_type, idempotency_key) DO NOTHING
                """,
                (tenant_id, event_id, delivery_id, idempotency_key, Jsonb({"delivery_id": delivery_id})),
            )
        row = active.execute(
            """
            SELECT delivery_id, template, status, created_at
            FROM email_deliveries WHERE tenant_id = %s AND idempotency_key = %s
            """,
            (tenant_id, idempotency_key),
        ).fetchone()
    return dict(row)


def deliver_email(*, tenant_id: str, delivery_id: str) -> dict[str, Any]:
    with connection() as active:
        row = active.execute(
            """
            SELECT recipient_ciphertext, template, template_data, template_data_ciphertext, status
            FROM email_deliveries WHERE tenant_id = %s AND delivery_id = %s FOR UPDATE
            """,
            (tenant_id, delivery_id),
        ).fetchone()
        if not row or row["status"] not in {"queued", "failed"}:
            raise CommunicationError("Email delivery is not sendable")
        active.execute(
            "UPDATE email_deliveries SET status = 'sending', attempt_count = attempt_count + 1 WHERE tenant_id = %s AND delivery_id = %s",
            (tenant_id, delivery_id),
        )
    template_data = (
        json.loads(decrypt_pii(row["template_data_ciphertext"], tenant_id=tenant_id))
        if row["template_data_ciphertext"]
        else dict(row["template_data"])
    )
    subject, body = render_template(row["template"], template_data)
    sender = os.getenv("TRANSACTIONAL_FROM_EMAIL", "")
    host = os.getenv("SMTP_HOST", "")
    if not sender or not host:
        raise CommunicationError("Transactional email is not configured")
    message = EmailMessage()
    recipient = decrypt_pii(row["recipient_ciphertext"], tenant_id=tenant_id)
    message["Subject"], message["From"], message["To"] = subject, sender, recipient
    message.set_content(body)
    try:
        with smtplib.SMTP_SSL(host, int(os.getenv("SMTP_PORT", "465")), timeout=20) as smtp:
            username, password = os.getenv("SMTP_USERNAME", ""), os.getenv("SMTP_PASSWORD", "")
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
    except Exception as exc:  # noqa: BLE001
        with connection() as active:
            active.execute(
                "UPDATE email_deliveries SET status = 'failed', last_error_code = 'smtp_failed' WHERE tenant_id = %s AND delivery_id = %s",
                (tenant_id, delivery_id),
            )
        raise CommunicationError("Transactional email delivery failed") from exc
    with connection() as active:
        active.execute(
            "UPDATE email_deliveries SET status = 'delivered', delivered_at = now(), last_error_code = NULL WHERE tenant_id = %s AND delivery_id = %s",
            (tenant_id, delivery_id),
        )
    return {"delivery_id": delivery_id, "status": "delivered"}


def record_provider_event(event: dict[str, Any]) -> dict[str, Any]:
    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    email = str(event.get("email") or "")
    if not event_id or event_type not in {"bounce", "complaint", "delivered"}:
        raise CommunicationError("Invalid email provider event")
    email_hash = _email_hash(email) if email else None
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
    with connection() as active:
        active.execute(
            """
            INSERT INTO email_events (provider, provider_event_id, event_type, email_hash, payload_sha256)
            VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING
            """,
            (str(event.get("provider") or "generic"), event_id, event_type, email_hash, hashlib.sha256(canonical).hexdigest()),
        )
        if event_type in {"bounce", "complaint"} and email_hash:
            active.execute(
                """
                INSERT INTO email_suppressions (email_hash, reason, provider_event_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (email_hash) DO UPDATE SET reason = EXCLUDED.reason,
                    provider_event_id = EXCLUDED.provider_event_id
                """,
                (email_hash, event_type, event_id),
            )
    return {"processed": True, "event_type": event_type, "suppressed": event_type in {"bounce", "complaint"}}
