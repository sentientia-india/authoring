import os

import pytest

from course_mcp_server.analytics import (
    account_dashboard,
    course_analytics,
    funnel_analytics,
    question_analytics,
    schedule_report,
)
from course_mcp_server.database import database_url
from course_mcp_server.hosted_repository import append_event, capture_lead, create_release
from scripts.apply_migrations import apply


pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration only")


def test_tenant_scoped_course_question_account_funnel_and_schedules():
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
    report = schedule_report(
        tenant_id="tenant-analytics",
        report_type="course",
        release_id=release["release_id"],
        cadence="weekly",
        recipients=["owner@example.com"],
    )
    assert report["status"] == "active"
