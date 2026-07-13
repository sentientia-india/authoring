import os
import secrets
from datetime import datetime, timedelta, timezone

import pytest

from course_mcp_server.analytics import (
    account_dashboard,
    analytics_quality_dashboard,
    course_analytics,
    funnel_analytics,
    learner_timeline,
    question_analytics,
    schedule_report,
)
from course_mcp_server.database import database_url
from course_mcp_server.database import connection
from course_mcp_server.analytics_worker import process_due_reports
from course_mcp_server.hosted_repository import (
    append_event,
    capture_lead,
    create_release,
    enroll_learner,
    get_or_create_learner,
    record_event_rejection,
    save_attempt_state,
)
from scripts.apply_migrations import apply


pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration only")


def test_tenant_scoped_course_question_account_funnel_and_schedules(tmp_path, monkeypatch):
    apply(database_url())
    release = create_release(
        tenant_id="tenant-analytics",
        course_id="course_analytics",
        release_id="release_analytics",
        object_key="tenants/tenant-analytics/releases/release_analytics/course.zip",
        package_sha256="c" * 64,
    )
    for event_type, payload in (
        ("attempt", {}),
        ("score", {"score": 80}),
        ("interaction", {"interaction": {"question_id": "q1", "correct": True}}),
        ("completion", {}),
    ):
        append_event(
            tenant_id="tenant-analytics",
            release_id=release["release_id"],
            event_type=event_type,
            learner_hash="learner-analytics",
            payload=payload,
        )
    capture_lead(
        tenant_id="tenant-analytics", release_id=release["release_id"], email="lead@example.com"
    )
    assert course_analytics(tenant_id="tenant-analytics", release_id=release["release_id"])[
        "average_score"
    ] == 80.0
    assert question_analytics(tenant_id="tenant-analytics", release_id=release["release_id"])[0][
        "correct_rate"
    ] == 100.0
    assert funnel_analytics(tenant_id="tenant-analytics", release_id=release["release_id"])["leads"] == 1
    assert account_dashboard(tenant_id="tenant-analytics")["releases"] == 1
    assert account_dashboard(tenant_id="tenant-other")["releases"] == 0
    assert course_analytics(tenant_id="tenant-other", release_id=release["release_id"])["attempts"] == 0
    assert question_analytics(tenant_id="tenant-other", release_id=release["release_id"]) == []
    assert funnel_analytics(tenant_id="tenant-other", release_id=release["release_id"])["leads"] == 0
    report = schedule_report(
        tenant_id="tenant-analytics",
        report_type="course",
        release_id=release["release_id"],
        cadence="weekly",
        recipients=["owner@example.com"],
    )
    assert report["status"] == "active"
    with connection() as active:
        stored = active.execute(
            "SELECT recipient_ciphertexts FROM scheduled_reports WHERE tenant_id = %s AND report_id = %s",
            ("tenant-analytics", report["report_id"]),
        ).fetchone()
        active.execute(
            "UPDATE scheduled_reports SET next_run_at = now() WHERE tenant_id = %s AND report_id = %s",
            ("tenant-analytics", report["report_id"]),
        )
    assert stored["recipient_ciphertexts"][0].startswith("v1:")
    assert "owner@example.com" not in stored["recipient_ciphertexts"][0]
    monkeypatch.setenv("OBJECT_STORE_LOCAL_ROOT", str(tmp_path / "objects"))
    monkeypatch.delenv("OBJECT_STORE_BUCKET", raising=False)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://courses.example.com")
    summary = process_due_reports()
    assert summary["succeeded"] == 1
    assert summary["emails_queued"] == 1
    assert list((tmp_path / "objects").rglob("course.csv"))


def test_learner_timeline_and_ingestion_quality_cover_late_duplicate_and_rejected_events():
    apply(database_url())
    suffix = secrets.token_hex(4)
    tenant = f"tenant-quality-{suffix}"
    release = create_release(
        tenant_id=tenant,
        course_id=f"course-quality-{suffix}",
        release_id=f"release-quality-{suffix}",
        object_key=f"tenants/{tenant}/releases/release-quality/course.zip",
        package_sha256="e" * 64,
    )
    learner = get_or_create_learner(
        tenant_id=tenant, identity_type="email", identity=f"learner-{suffix}@example.com"
    )
    enrollment = enroll_learner(
        tenant_id=tenant,
        learner_id=learner["learner_id"],
        release_id=release["release_id"],
        entitlement_source="invitation",
    )
    attempt = save_attempt_state(
        tenant_id=tenant,
        enrollment_id=enrollment["enrollment_id"],
        attempt_number=1,
    )
    event = append_event(
        tenant_id=tenant,
        release_id=release["release_id"],
        event_type="progress",
        learner_hash="learner-quality",
        enrollment_id=enrollment["enrollment_id"],
        attempt_id=attempt["attempt_id"],
        occurred_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        payload={"idempotency_key": f"quality-{suffix}", "progress": 50},
    )
    duplicate = append_event(
        tenant_id=tenant,
        release_id=release["release_id"],
        event_type="progress",
        learner_hash="learner-quality",
        enrollment_id=enrollment["enrollment_id"],
        attempt_id=attempt["attempt_id"],
        payload={"idempotency_key": f"quality-{suffix}", "progress": 50},
    )
    assert event["duplicate"] is False
    assert duplicate["duplicate"] is True
    record_event_rejection(tenant_id=tenant, release_id=release["release_id"], reason_code="invalid_payload")
    timeline = learner_timeline(tenant_id=tenant, learner_id=learner["learner_id"])
    assert [item["event_type"] for item in timeline] == ["progress"]
    quality = analytics_quality_dashboard(tenant_id=tenant, release_id=release["release_id"])
    assert quality["accepted"] == 1
    assert quality["duplicates"] == 1
    assert quality["rejected"] == 1
    assert quality["late_events"] == 1
    assert quality["status"] == "failed"
