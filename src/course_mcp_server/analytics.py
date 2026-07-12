from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.types.json import Jsonb

from .database import connection


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
    *, tenant_id: str, report_type: str, release_id: str | None, cadence: str, recipients: list[str]
) -> dict[str, Any]:
    if report_type not in REPORT_TYPES or cadence not in {"daily", "weekly", "monthly"}:
        raise ValueError("Invalid report schedule")
    hashes = [hashlib.sha256(email.strip().lower().encode()).hexdigest() for email in recipients]
    raw = f"{tenant_id}:{report_type}:{release_id}:{cadence}:{','.join(sorted(hashes))}".encode()
    report_id = f"report_{hashlib.sha256(raw).hexdigest()[:24]}"
    days = {"daily": 1, "weekly": 7, "monthly": 30}[cadence]
    next_run = datetime.now(timezone.utc) + timedelta(days=days)
    with connection() as active:
        row = active.execute(
            """
            INSERT INTO scheduled_reports
                (tenant_id, report_id, report_type, release_id, cadence, recipient_hashes, next_run_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, report_id) DO UPDATE
            SET status = 'active', next_run_at = EXCLUDED.next_run_at
            RETURNING report_id, report_type, release_id, cadence, status, next_run_at
            """,
            (tenant_id, report_id, report_type, release_id, cadence, Jsonb(hashes), next_run),
        ).fetchone()
    return dict(row)


def due_reports(*, limit: int = 50) -> list[dict[str, Any]]:
    with connection() as active:
        rows = active.execute(
            """
            SELECT tenant_id, report_id, report_type, release_id, cadence, recipient_hashes
            FROM scheduled_reports
            WHERE status = 'active' AND next_run_at <= now()
            ORDER BY next_run_at LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
