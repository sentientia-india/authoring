from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from .database import connection, ensure_tenant


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_release(
    *,
    tenant_id: str,
    course_id: str,
    release_id: str,
    object_key: str,
    package_sha256: str,
) -> dict[str, Any]:
    with connection() as active:
        ensure_tenant(active, tenant_id)
        active.execute(
            """
            INSERT INTO hosted_releases
                (tenant_id, release_id, course_id, package_object_key, package_sha256)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, course_id, package_sha256) DO NOTHING
            """,
            (tenant_id, release_id, course_id, object_key, package_sha256),
        )
        row = active.execute(
            """
            SELECT tenant_id, release_id, course_id, package_object_key, package_sha256, status, published_at
            FROM hosted_releases
            WHERE tenant_id = %s AND course_id = %s AND package_sha256 = %s
            """,
            (tenant_id, course_id, package_sha256),
        ).fetchone()
    return dict(row)


def create_grant(*, tenant_id: str, release_id: str, token: str, mode: str) -> dict[str, Any]:
    grant_id = f"grant_{uuid4().hex}"
    with connection() as active:
        row = active.execute(
            """
            INSERT INTO share_grants (tenant_id, grant_id, release_id, mode, token_hash)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING tenant_id, grant_id, release_id, mode, created_at
            """,
            (tenant_id, grant_id, release_id, mode, token_hash(token)),
        ).fetchone()
    return dict(row)


def resolve_grant(token: str) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc)
    with connection() as active:
        row = active.execute(
            """
            SELECT grants.tenant_id, grants.grant_id, grants.release_id, grants.mode,
                   releases.course_id, releases.package_object_key, releases.package_sha256
            FROM share_grants AS grants
            JOIN hosted_releases AS releases
              ON releases.tenant_id = grants.tenant_id AND releases.release_id = grants.release_id
            WHERE grants.token_hash = %s
              AND grants.revoked_at IS NULL
              AND (grants.expires_at IS NULL OR grants.expires_at > %s)
              AND (grants.maximum_uses IS NULL OR grants.use_count < grants.maximum_uses)
              AND releases.status = 'published'
            """,
            (token_hash(token), now),
        ).fetchone()
    return dict(row) if row else None


def grant_entitlement(*, tenant_id: str, release_id: str, purchaser: str, access_token: str) -> dict[str, Any]:
    entitlement_id = f"ent_{uuid4().hex}"
    with connection() as active:
        row = active.execute(
            """
            INSERT INTO hosted_entitlements
                (tenant_id, entitlement_id, release_id, subject_hash, access_token_hash, source)
            VALUES (%s, %s, %s, %s, %s, 'purchase')
            RETURNING tenant_id, entitlement_id, release_id, status, effective_at
            """,
            (
                tenant_id,
                entitlement_id,
                release_id,
                hashlib.sha256(purchaser.lower().encode()).hexdigest(),
                token_hash(access_token),
            ),
        ).fetchone()
    return dict(row)


def has_entitlement(*, tenant_id: str, release_id: str, access_token: str | None) -> bool:
    if not access_token:
        return False
    with connection() as active:
        row = active.execute(
            """
            SELECT 1 FROM hosted_entitlements
            WHERE tenant_id = %s AND release_id = %s AND access_token_hash = %s
              AND status = 'active' AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > now())
            """,
            (tenant_id, release_id, token_hash(access_token)),
        ).fetchone()
    return bool(row)


def append_event(
    *, tenant_id: str, release_id: str, event_type: str, learner_hash: str, payload: dict[str, Any]
) -> dict[str, Any]:
    idempotency_key = str(payload.get("idempotency_key") or f"{event_type}:{uuid4().hex}")
    event_id = f"learn_evt_{hashlib.sha256(f'{tenant_id}:{idempotency_key}'.encode()).hexdigest()[:24]}"
    event_payload = {**payload, "learner_hash": learner_hash}
    with connection() as active:
        active.execute(
            """
            INSERT INTO learner_events
                (tenant_id, event_id, release_id, event_type, idempotency_key, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            """,
            (tenant_id, event_id, release_id, event_type, idempotency_key, Jsonb(event_payload)),
        )
        row = active.execute(
            """
            SELECT event_id, event_type, payload, occurred_at
            FROM learner_events WHERE tenant_id = %s AND idempotency_key = %s
            """,
            (tenant_id, idempotency_key),
        ).fetchone()
    return dict(row)


def dashboard(*, tenant_id: str, release_id: str) -> dict[str, Any]:
    with connection() as active:
        rows = active.execute(
            "SELECT event_type, payload FROM learner_events WHERE tenant_id = %s AND release_id = %s",
            (tenant_id, release_id),
        ).fetchall()
    learners = {row["payload"].get("learner_hash") for row in rows}
    scores = [int(row["payload"].get("score", 0)) for row in rows if row["event_type"] == "score"]
    return {
        "learners": len(learners - {None}),
        "completions": sum(row["event_type"] == "completion" for row in rows),
        "attempts": sum(row["event_type"] == "attempt" for row in rows),
        "average_score": round(sum(scores) / len(scores), 2) if scores else None,
    }


def capture_lead(*, tenant_id: str, release_id: str, email: str) -> dict[str, Any]:
    email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
    lead_id = f"lead_{hashlib.sha256(f'{tenant_id}:{release_id}:{email_hash}'.encode()).hexdigest()[:24]}"
    with connection() as active:
        row = active.execute(
            """
            INSERT INTO captured_leads (tenant_id, lead_id, release_id, email_hash)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tenant_id, release_id, email_hash) DO UPDATE SET email_hash = EXCLUDED.email_hash
            RETURNING lead_id, release_id, email_hash, captured_at
            """,
            (tenant_id, lead_id, release_id, email_hash),
        ).fetchone()
    return dict(row)


def get_or_create_learner(*, tenant_id: str, identity_type: str, identity: str) -> dict[str, Any]:
    identity_hash = hashlib.sha256(identity.strip().lower().encode()).hexdigest()
    learner_id = f"learner_{identity_hash[:24]}"
    with connection() as active:
        ensure_tenant(active, tenant_id)
        active.execute(
            """
            INSERT INTO learner_identities (tenant_id, learner_id, identity_type, identity_hash)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tenant_id, identity_type, identity_hash) DO NOTHING
            """,
            (tenant_id, learner_id, identity_type, identity_hash),
        )
        row = active.execute(
            """
            SELECT tenant_id, learner_id, identity_type, created_at
            FROM learner_identities
            WHERE tenant_id = %s AND identity_type = %s AND identity_hash = %s
            """,
            (tenant_id, identity_type, identity_hash),
        ).fetchone()
    return dict(row)


def enroll_learner(
    *, tenant_id: str, learner_id: str, release_id: str, entitlement_source: str
) -> dict[str, Any]:
    raw = f"{tenant_id}:{learner_id}:{release_id}:{entitlement_source}".encode()
    enrollment_id = f"enroll_{hashlib.sha256(raw).hexdigest()[:24]}"
    with connection() as active:
        active.execute(
            """
            INSERT INTO enrollments
                (tenant_id, enrollment_id, learner_id, release_id, entitlement_source)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, learner_id, release_id, entitlement_source) DO NOTHING
            """,
            (tenant_id, enrollment_id, learner_id, release_id, entitlement_source),
        )
        row = active.execute(
            """
            SELECT tenant_id, enrollment_id, learner_id, release_id, entitlement_source, status, enrolled_at
            FROM enrollments
            WHERE tenant_id = %s AND learner_id = %s AND release_id = %s AND entitlement_source = %s
            """,
            (tenant_id, learner_id, release_id, entitlement_source),
        ).fetchone()
    return dict(row)


def save_attempt_state(
    *,
    tenant_id: str,
    enrollment_id: str,
    attempt_number: int,
    completion_status: str | None = None,
    success_status: str | None = None,
    score: float | None = None,
    location: str | None = None,
    suspend_data: str | None = None,
    session_seconds: int = 0,
) -> dict[str, Any]:
    raw = f"{tenant_id}:{enrollment_id}:{attempt_number}".encode()
    attempt_id = f"attempt_{hashlib.sha256(raw).hexdigest()[:24]}"
    with connection() as active:
        active.execute(
            """
            INSERT INTO learner_attempts
                (tenant_id, attempt_id, enrollment_id, attempt_number, completion_status,
                 success_status, score, location, suspend_data, session_seconds)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, enrollment_id, attempt_number) DO UPDATE
            SET completion_status = COALESCE(EXCLUDED.completion_status, learner_attempts.completion_status),
                success_status = COALESCE(EXCLUDED.success_status, learner_attempts.success_status),
                score = COALESCE(EXCLUDED.score, learner_attempts.score),
                location = COALESCE(EXCLUDED.location, learner_attempts.location),
                suspend_data = COALESCE(EXCLUDED.suspend_data, learner_attempts.suspend_data),
                session_seconds = learner_attempts.session_seconds + EXCLUDED.session_seconds,
                updated_at = now(), version = learner_attempts.version + 1
            """,
            (
                tenant_id,
                attempt_id,
                enrollment_id,
                attempt_number,
                completion_status,
                success_status,
                score,
                location,
                suspend_data,
                max(0, session_seconds),
            ),
        )
        row = active.execute(
            """
            SELECT tenant_id, attempt_id, enrollment_id, attempt_number, completion_status,
                   success_status, score, location, suspend_data, session_seconds, version
            FROM learner_attempts
            WHERE tenant_id = %s AND enrollment_id = %s AND attempt_number = %s
            """,
            (tenant_id, enrollment_id, attempt_number),
        ).fetchone()
    return dict(row)


def revoke_enrollment(*, tenant_id: str, enrollment_id: str) -> bool:
    with connection() as active:
        result = active.execute(
            """
            UPDATE enrollments SET status = 'revoked', revoked_at = now()
            WHERE tenant_id = %s AND enrollment_id = %s AND revoked_at IS NULL
            """,
            (tenant_id, enrollment_id),
        )
    return result.rowcount == 1


def revoke_grant(*, tenant_id: str, grant_id: str) -> bool:
    with connection() as active:
        result = active.execute(
            """
            UPDATE share_grants SET revoked_at = now()
            WHERE tenant_id = %s AND grant_id = %s AND revoked_at IS NULL
            """,
            (tenant_id, grant_id),
        )
    return result.rowcount == 1
