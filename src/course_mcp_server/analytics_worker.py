from __future__ import annotations

import hashlib
import io
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .analytics import (
    account_dashboard,
    course_analytics,
    due_reports,
    export_csv,
    funnel_analytics,
    learner_timeline,
    question_analytics,
)
from .communication import queue_email
from .database import connection
from .object_store import object_key, object_store
from .pii_crypto import decrypt_pii


def _rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    tenant_id = report["tenant_id"]
    release_id = report.get("release_id")
    report_type = report["report_type"]
    if report_type == "account":
        return [account_dashboard(tenant_id=tenant_id)]
    if report_type == "learner":
        learner_id = str((report.get("report_parameters") or {}).get("learner_id") or "")
        return learner_timeline(tenant_id=tenant_id, learner_id=learner_id)
    if not release_id:
        raise ValueError("Release-scoped report requires release_id")
    if report_type == "course":
        return [course_analytics(tenant_id=tenant_id, release_id=release_id)]
    if report_type == "question":
        return question_analytics(tenant_id=tenant_id, release_id=release_id)
    if report_type == "funnel":
        return [funnel_analytics(tenant_id=tenant_id, release_id=release_id)]
    raise ValueError("Unsupported report type")


def process_due_reports(*, limit: int = 25) -> dict[str, int]:
    summary = {"due": 0, "succeeded": 0, "failed": 0, "emails_queued": 0}
    base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    for report in due_reports(limit=limit):
        summary["due"] += 1
        run_id = f"report_run_{uuid4().hex}"
        with connection() as active:
            active.execute(
                """
                INSERT INTO analytics_report_runs (tenant_id, run_id, report_id, status)
                VALUES (%s, %s, %s, 'running')
                """,
                (report["tenant_id"], run_id, report["report_id"]),
            )
        try:
            rows = _rows(report)
            payload = export_csv(rows).encode()
            key = object_key(
                tenant_id=report["tenant_id"],
                kind="reports",
                object_id=run_id,
                filename=f"{report['report_type']}.csv",
            )
            stored = object_store().put(key, io.BytesIO(payload))
            next_run = datetime.now(timezone.utc) + timedelta(
                days={"daily": 1, "weekly": 7, "monthly": 30}[report["cadence"]]
            )
            with connection() as active:
                active.execute(
                    """
                    UPDATE analytics_report_runs
                    SET status = 'succeeded', object_key = %s, sha256 = %s,
                        row_count = %s, completed_at = now()
                    WHERE tenant_id = %s AND run_id = %s
                    """,
                    (stored["object_key"], stored["sha256"], len(rows), report["tenant_id"], run_id),
                )
                active.execute(
                    """
                    UPDATE scheduled_reports SET last_run_at = now(), next_run_at = %s
                    WHERE tenant_id = %s AND report_id = %s
                    """,
                    (next_run, report["tenant_id"], report["report_id"]),
                )
            for ciphertext in report["recipient_ciphertexts"]:
                recipient = decrypt_pii(ciphertext, tenant_id=report["tenant_id"])
                queue_email(
                    tenant_id=report["tenant_id"],
                    recipient=recipient,
                    template="report",
                    data={
                        "report_type": report["report_type"],
                        "action_url": f"{base_url}/api/analytics/report-runs/{run_id}" if base_url else run_id,
                    },
                    idempotency_key=hashlib.sha256(f"{run_id}:{recipient}".encode()).hexdigest(),
                )
                summary["emails_queued"] += 1
            summary["succeeded"] += 1
        except Exception as exc:  # noqa: BLE001
            with connection() as active:
                active.execute(
                    """
                    UPDATE analytics_report_runs
                    SET status = 'failed', error_code = %s, completed_at = now()
                    WHERE tenant_id = %s AND run_id = %s
                    """,
                    (type(exc).__name__[:120], report["tenant_id"], run_id),
                )
            summary["failed"] += 1
    return summary


def main() -> None:
    interval = max(10.0, float(os.getenv("REPORT_WORKER_POLL_SECONDS", "60")))
    while True:
        process_due_reports()
        time.sleep(interval)


if __name__ == "__main__":
    main()
