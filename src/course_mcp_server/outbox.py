from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.types.json import Jsonb

from .database import connection, ensure_tenant


def _event_id(tenant_id: str, event_type: str, idempotency_key: str) -> str:
    raw = f"{tenant_id}:{event_type}:{idempotency_key}".encode()
    return f"evt_{hashlib.sha256(raw).hexdigest()[:24]}"


def publish_event(
    *,
    tenant_id: str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    sequence: int,
    idempotency_key: str,
    payload: dict[str, Any],
    event_version: int = 1,
) -> dict[str, Any]:
    event_id = _event_id(tenant_id, event_type, idempotency_key)
    with connection() as active:
        ensure_tenant(active, tenant_id)
        active.execute(
            """
            INSERT INTO outbox_events
                (tenant_id, event_id, event_type, event_version, aggregate_type,
                 aggregate_id, sequence, idempotency_key, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, event_type, idempotency_key) DO NOTHING
            """,
            (
                tenant_id,
                event_id,
                event_type,
                event_version,
                aggregate_type,
                aggregate_id,
                sequence,
                idempotency_key,
                Jsonb(payload),
            ),
        )
        row = active.execute(
            """
            SELECT event_id, event_type, aggregate_type, aggregate_id, sequence, payload,
                   delivered_at, attempt_count
            FROM outbox_events
            WHERE tenant_id = %s AND event_type = %s AND idempotency_key = %s
            """,
            (tenant_id, event_type, idempotency_key),
        ).fetchone()
    return dict(row)


def claim_events(*, limit: int = 25, lease_seconds: int = 60) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    lease_until = now + timedelta(seconds=lease_seconds)
    with connection() as active:
        rows = active.execute(
            """
            WITH claimable AS (
                SELECT tenant_id, event_id
                FROM outbox_events
                WHERE delivered_at IS NULL
                  AND dead_lettered_at IS NULL
                  AND available_at <= %s
                  AND (leased_until IS NULL OR leased_until < %s)
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT %s
            )
            UPDATE outbox_events AS events
            SET leased_until = %s,
                attempt_count = events.attempt_count + 1
            FROM claimable
            WHERE events.tenant_id = claimable.tenant_id
              AND events.event_id = claimable.event_id
            RETURNING events.tenant_id, events.event_id, events.event_type,
                      events.event_version, events.aggregate_type, events.aggregate_id,
                      events.sequence, events.payload, events.attempt_count
            """,
            (now, now, limit, lease_until),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_delivered(*, tenant_id: str, event_id: str) -> None:
    with connection() as active:
        result = active.execute(
            """
            UPDATE outbox_events
            SET delivered_at = now(), leased_until = NULL, last_error_code = NULL
            WHERE tenant_id = %s AND event_id = %s AND delivered_at IS NULL
            """,
            (tenant_id, event_id),
        )
        if result.rowcount != 1:
            raise LookupError("Outbox event not found or already delivered")


def release_failed(
    *, tenant_id: str, event_id: str, error_code: str, delay_seconds: int = 30, max_attempts: int = 5
) -> dict[str, Any]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    available_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    with connection() as active:
        row = active.execute(
            """
            SELECT event_type, aggregate_type, aggregate_id, payload, attempt_count
            FROM outbox_events
            WHERE tenant_id = %s AND event_id = %s
              AND delivered_at IS NULL AND dead_lettered_at IS NULL
            FOR UPDATE
            """,
            (tenant_id, event_id),
        ).fetchone()
        if not row:
            raise LookupError("Outbox event not found or no longer retryable")
        if row["attempt_count"] >= max_attempts:
            active.execute(
                """
                INSERT INTO outbox_dead_letters
                    (tenant_id, event_id, event_type, aggregate_type, aggregate_id,
                     payload, attempt_count, error_code)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, event_id) DO NOTHING
                """,
                (
                    tenant_id,
                    event_id,
                    row["event_type"],
                    row["aggregate_type"],
                    row["aggregate_id"],
                    Jsonb(dict(row["payload"])),
                    row["attempt_count"],
                    error_code[:120],
                ),
            )
            active.execute(
                """
                UPDATE outbox_events
                SET leased_until = NULL, dead_lettered_at = now(), last_error_code = %s
                WHERE tenant_id = %s AND event_id = %s
                """,
                (error_code[:120], tenant_id, event_id),
            )
            return {"status": "dead_lettered", "attempt_count": row["attempt_count"]}
        active.execute(
            """
            UPDATE outbox_events
            SET leased_until = NULL, available_at = %s, last_error_code = %s
            WHERE tenant_id = %s AND event_id = %s AND delivered_at IS NULL
            """,
            (available_at, error_code[:120], tenant_id, event_id),
        )
    return {"status": "retry_scheduled", "attempt_count": row["attempt_count"]}


def list_dead_letters(*, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with connection() as active:
        rows = active.execute(
            """
            SELECT event_id, event_type, aggregate_type, aggregate_id, payload,
                   attempt_count, error_code, failed_at
            FROM outbox_dead_letters
            WHERE tenant_id = %s AND redriven_at IS NULL
            ORDER BY failed_at LIMIT %s
            """,
            (tenant_id, max(1, min(limit, 500))),
        ).fetchall()
    return [dict(row) for row in rows]


def redrive_dead_letter(*, tenant_id: str, event_id: str) -> dict[str, Any]:
    with connection() as active:
        row = active.execute(
            """
            UPDATE outbox_dead_letters
            SET redriven_at = now()
            WHERE tenant_id = %s AND event_id = %s AND redriven_at IS NULL
            RETURNING event_id
            """,
            (tenant_id, event_id),
        ).fetchone()
        if not row:
            raise LookupError("Dead-letter event not found or already redriven")
        active.execute(
            """
            UPDATE outbox_events
            SET dead_lettered_at = NULL, leased_until = NULL, available_at = now(),
                attempt_count = 0, last_error_code = NULL
            WHERE tenant_id = %s AND event_id = %s AND delivered_at IS NULL
            """,
            (tenant_id, event_id),
        )
    return {"event_id": event_id, "status": "redriven"}


def canonical_payload(event: dict[str, Any]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"))
