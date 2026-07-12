import os

import pytest

from course_mcp_server.database import database_url
from course_mcp_server.outbox import claim_events, mark_delivered, publish_event, release_failed
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
