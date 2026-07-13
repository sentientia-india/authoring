from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from uuid import uuid4
from datetime import date, datetime, timedelta, timezone
from typing import Any

from psycopg.types.json import Jsonb

from .database import connection
from .pii_crypto import encrypt_pii
from .object_store import object_store


REPORT_TYPES = {"course", "learner", "question", "account", "funnel"}


def account_dashboard(*, tenant_id: str) -> dict[str, Any]:
    with connection() as active:
        row = active.execute(
            """
            SELECT
                (SELECT count(*) FROM hosted_releases WHERE tenant_id = %s AND status = 'published') AS releases,
                (SELECT count(*) FROM learner_identities WHERE tenant_id = %s) AS learners,
                (SELECT count(*) FROM enrollments WHERE tenant_id = %s AND status IN ('active', 'completed')) AS enrollments,
                (SELECT count(*) FROM learner_events WHERE tenant_id = %s AND event_type = 'completion') AS completions
            """,
            (tenant_id, tenant_id, tenant_id, tenant_id),
        ).fetchone()
    return dict(row)


def course_analytics(*, tenant_id: str, release_id: str) -> dict[str, Any]:
    with connection() as active:
        rows = active.execute(
            "SELECT event_type, payload FROM learner_events WHERE tenant_id = %s AND release_id = %s",
            (tenant_id, release_id),
        ).fetchall()
    learners = {row["payload"].get("learner_hash") for row in rows} - {None}
    scores = [float(row["payload"].get("score", 0)) for row in rows if row["event_type"] == "score"]
    return {
        "release_id": release_id,
        "learners": len(learners),
        "attempts": sum(row["event_type"] == "attempt" for row in rows),
        "completions": sum(row["event_type"] == "completion" for row in rows),
        "average_score": round(sum(scores) / len(scores), 2) if scores else None,
        "completion_rate": round(
            100 * sum(row["event_type"] == "completion" for row in rows) / max(1, len(learners)), 2
        ),
    }


def question_analytics(*, tenant_id: str, release_id: str) -> list[dict[str, Any]]:
    with connection() as active:
        rows = active.execute(
            """
            SELECT payload FROM learner_events
            WHERE tenant_id = %s AND release_id = %s AND event_type = 'interaction'
            """,
            (tenant_id, release_id),
        ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        interaction = row["payload"].get("interaction") or {}
        question_id = str(interaction.get("question_id") or "unknown")
        bucket = grouped.setdefault(question_id, {"question_id": question_id, "responses": 0, "correct": 0})
        bucket["responses"] += 1
        bucket["correct"] += int(bool(interaction.get("correct")))
    return [
        {**bucket, "correct_rate": round(100 * bucket["correct"] / max(1, bucket["responses"]), 2)}
        for bucket in sorted(grouped.values(), key=lambda item: item["question_id"])
    ]


def funnel_analytics(*, tenant_id: str, release_id: str) -> dict[str, Any]:
    with connection() as active:
        row = active.execute(
            """
            SELECT
                (SELECT count(*) FROM captured_leads WHERE tenant_id = %s AND release_id = %s) AS leads,
                (SELECT count(*) FROM enrollments WHERE tenant_id = %s AND release_id = %s) AS enrollments,
                (SELECT count(*) FROM learner_events WHERE tenant_id = %s AND release_id = %s AND event_type = 'attempt') AS starts,
                (SELECT count(*) FROM learner_events WHERE tenant_id = %s AND release_id = %s AND event_type = 'completion') AS completions
            """,
            (tenant_id, release_id, tenant_id, release_id, tenant_id, release_id, tenant_id, release_id),
        ).fetchone()
    return dict(row)


def learner_timeline(*, tenant_id: str, learner_id: str) -> list[dict[str, Any]]:
    with connection() as active:
        rows = active.execute(
            """
            SELECT events.event_id, events.release_id, events.enrollment_id, events.attempt_id,
                   events.event_type, events.event_version, events.occurred_at, events.received_at,
                   events.payload - 'learner_hash' AS payload
            FROM learner_events AS events
            JOIN enrollments AS enrollment
              ON enrollment.tenant_id = events.tenant_id
             AND enrollment.enrollment_id = events.enrollment_id
            WHERE events.tenant_id = %s AND enrollment.learner_id = %s
            ORDER BY events.occurred_at, events.event_id
            """,
            (tenant_id, learner_id),
        ).fetchall()
    return [dict(row) for row in rows]


def analytics_quality_dashboard(*, tenant_id: str, release_id: str | None = None) -> dict[str, Any]:
    release_clause = " AND release_id = %s" if release_id else ""
    parameters: tuple[Any, ...] = (tenant_id, release_id) if release_id else (tenant_id,)
    with connection() as active:
        observation = active.execute(
            f"""
            SELECT count(*) FILTER (WHERE outcome = 'accepted') AS accepted,
                   count(*) FILTER (WHERE outcome = 'duplicate') AS duplicates,
                   count(*) FILTER (WHERE outcome = 'rejected') AS rejected
            FROM analytics_ingestion_observations
            WHERE tenant_id = %s{release_clause}
            """,  # nosec B608 - clause is selected from a constant
            parameters,
        ).fetchone()
        events = active.execute(
            f"""
            SELECT count(*) AS stored_events,
                   count(*) FILTER (WHERE received_at - occurred_at > interval '5 minutes') AS late_events,
                   count(*) FILTER (
                       WHERE event_type IN ('progress', 'interaction', 'answer', 'score', 'completion', 'complete')
                         AND (enrollment_id IS NULL OR attempt_id IS NULL)
                   ) AS missing_context
            FROM learner_events
            WHERE tenant_id = %s{release_clause}
            """,  # nosec B608 - clause is selected from a constant
            parameters,
        ).fetchone()
        result = {**dict(observation), **dict(events)}
        failed = bool(result["rejected"] or result["missing_context"])
        active.execute(
            """
            INSERT INTO analytics_quality_checks
                (tenant_id, check_id, release_id, check_type, status, observed_value,
                 expected_value, details)
            VALUES (%s, %s, %s, 'ingestion_quality', %s, %s, 0, %s)
            """,
            (
                tenant_id,
                f"quality_{uuid4().hex}",
                release_id,
                "failed" if failed else "passed",
                result["rejected"] + result["missing_context"],
                Jsonb(result),
            ),
        )
    return {"status": "failed" if failed else "passed", **result}


def export_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    fields = sorted({key for row in rows for key in row})
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def schedule_report(
    *,
    tenant_id: str,
    report_type: str,
    release_id: str | None,
    cadence: str,
    recipients: list[str],
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if report_type not in REPORT_TYPES or cadence not in {"daily", "weekly", "monthly"}:
        raise ValueError("Invalid report schedule")
    if not 1 <= len(recipients) <= 20 or any(
        not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()) for email in recipients
    ):
        raise ValueError("Report schedule requires valid recipients")
    hashes = [hashlib.sha256(email.strip().lower().encode()).hexdigest() for email in recipients]
    ciphertexts = [encrypt_pii(email.strip().lower(), tenant_id=tenant_id) for email in recipients]
    parameters = parameters or {}
    if report_type == "learner" and not str(parameters.get("learner_id") or ""):
        raise ValueError("Learner reports require learner_id")
    parameter_json = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    raw = f"{tenant_id}:{report_type}:{release_id}:{cadence}:{','.join(sorted(hashes))}:{parameter_json}".encode()
    report_id = f"report_{hashlib.sha256(raw).hexdigest()[:24]}"
    days = {"daily": 1, "weekly": 7, "monthly": 30}[cadence]
    next_run = datetime.now(timezone.utc) + timedelta(days=days)
    with connection() as active:
        row = active.execute(
            """
            INSERT INTO scheduled_reports
                (tenant_id, report_id, report_type, release_id, cadence, recipient_hashes,
                 recipient_ciphertexts, report_parameters, next_run_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, report_id) DO UPDATE
            SET status = 'active', next_run_at = EXCLUDED.next_run_at
            RETURNING report_id, report_type, release_id, cadence, status, next_run_at
            """,
            (
                tenant_id,
                report_id,
                report_type,
                release_id,
                cadence,
                Jsonb(hashes),
                Jsonb(ciphertexts),
                Jsonb(parameters),
                next_run,
            ),
        ).fetchone()
    return dict(row)


def due_reports(*, limit: int = 50) -> list[dict[str, Any]]:
    with connection() as active:
        rows = active.execute(
            """
            WITH due AS (
                SELECT tenant_id, report_id
                FROM scheduled_reports
                WHERE status = 'active' AND next_run_at <= now()
                ORDER BY next_run_at
                FOR UPDATE SKIP LOCKED
                LIMIT %s
            )
            UPDATE scheduled_reports AS reports
            SET next_run_at = now() + interval '5 minutes'
            FROM due
            WHERE reports.tenant_id = due.tenant_id AND reports.report_id = due.report_id
            RETURNING reports.tenant_id, reports.report_id, reports.report_type,
                      reports.release_id, reports.cadence, reports.recipient_hashes,
                      reports.recipient_ciphertexts, reports.report_parameters
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def report_run_access(*, tenant_id: str, run_id: str) -> dict[str, str]:
    with connection() as active:
        row = active.execute(
            """
            SELECT object_key FROM analytics_report_runs
            WHERE tenant_id = %s AND run_id = %s AND status = 'succeeded'
            """,
            (tenant_id, run_id),
        ).fetchone()
    if not row or not row["object_key"]:
        raise LookupError("Report run not found")
    return object_store().access(row["object_key"])


def summarize_course_metrics(*, project_id: str, events: list[dict]) -> dict:
    """Preserve the portable, database-independent analytics summary contract."""
    scores = [int(event.get("score", 0)) for event in events if event.get("score") is not None]
    durations = [int(event.get("duration_seconds", 0)) for event in events]
    return {
        "project_id": project_id,
        "attempt_count": len(events),
        "completion_count": sum(1 for event in events if event.get("event_type") == "completed"),
        "average_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "time_spent_seconds": sum(durations),
        "learner_count": len({event.get("learner_id") for event in events if event.get("learner_id")}),
    }


def issue_certificate(
    *,
    project_id: str,
    learner_id: str,
    learner_name: str,
    course_title: str,
    score: int,
    valid_days: int,
) -> dict:
    """Preserve deterministic certificate metadata used by the renderer and tools."""
    issued = date.today()
    digest = hashlib.sha256(f"{project_id}:{learner_id}:{issued.isoformat()}".encode()).hexdigest()[:12]
    return {
        "certificate_id": f"cert_{digest}",
        "project_id": project_id,
        "learner_id": learner_id,
        "learner_name": learner_name,
        "course_title": course_title,
        "score": score,
        "issued_date": issued.isoformat(),
        "recertification_due_date": (issued + timedelta(days=valid_days)).isoformat(),
    }
