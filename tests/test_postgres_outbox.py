import os

import pytest

from course_mcp_server.database import database_url
from course_mcp_server.outbox import (
    claim_events,
    list_dead_letters,
    mark_delivered,
    publish_event,
    redrive_dead_letter,
    release_failed,
)
from scripts.apply_migrations import apply


pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration only")


def test_outbox_is_idempotent_leased_and_tenant_scoped():
    apply(database_url())
    kwargs = {
        "tenant_id": "tenant-outbox",
        "event_type": "course.published",
        "aggregate_type": "course",
        "aggregate_id": "course_1",
        "sequence": 1,
        "idempotency_key": "publish-course-1-v1",
        "payload": {"course_id": "course_1"},
    }
    first = publish_event(**kwargs)
    second = publish_event(**kwargs)
    assert first["event_id"] == second["event_id"]

    claimed = [event for event in claim_events(limit=10) if event["event_id"] == first["event_id"]]
    assert len(claimed) == 1
    assert claimed[0]["attempt_count"] == 1
    assert not [event for event in claim_events(limit=10) if event["event_id"] == first["event_id"]]

    release_failed(tenant_id="tenant-outbox", event_id=first["event_id"], error_code="temporary", delay_seconds=0)
    retried = [event for event in claim_events(limit=10) if event["event_id"] == first["event_id"]]
    assert retried[0]["attempt_count"] == 2
    mark_delivered(tenant_id="tenant-outbox", event_id=first["event_id"])
    assert not [event for event in claim_events(limit=10) if event["event_id"] == first["event_id"]]


def test_outbox_dead_letters_after_bounded_attempts_and_can_be_redriven():
    apply(database_url())
    event = publish_event(
        tenant_id="tenant-outbox-dlq",
        event_type="email.queued",
        aggregate_type="email_delivery",
        aggregate_id="mail_1",
        sequence=1,
        idempotency_key="mail-1",
        payload={"delivery_id": "mail_1"},
    )
    for expected_attempt in range(1, 4):
        claimed = [item for item in claim_events(limit=20) if item["event_id"] == event["event_id"]][0]
        assert claimed["attempt_count"] == expected_attempt
        result = release_failed(
            tenant_id="tenant-outbox-dlq",
            event_id=event["event_id"],
            error_code="smtp_unavailable",
            delay_seconds=0,
            max_attempts=3,
        )
    assert result["status"] == "dead_lettered"
    assert list_dead_letters(tenant_id="tenant-outbox-dlq")[0]["event_id"] == event["event_id"]
    assert list_dead_letters(tenant_id="another-tenant") == []
    assert not [item for item in claim_events(limit=20) if item["event_id"] == event["event_id"]]
    assert redrive_dead_letter(tenant_id="tenant-outbox-dlq", event_id=event["event_id"])["status"] == "redriven"
    redriven = [item for item in claim_events(limit=20) if item["event_id"] == event["event_id"]][0]
    assert redriven["attempt_count"] == 1
