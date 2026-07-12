import os

import pytest

from course_mcp_server.communication import queue_email, record_provider_event
from course_mcp_server.database import database_url
from scripts.apply_migrations import apply


pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration only")


def test_email_queue_is_idempotent_and_suppresses_bounces():
    apply(database_url())
    data = {"course_title": "Safety", "action_url": "https://example.com/course"}
    first = queue_email(
        tenant_id="tenant-email",
        recipient="learner@example.com",
        template="invitation",
        data=data,
        idempotency_key="invite-1",
    )
    second = queue_email(
        tenant_id="tenant-email",
        recipient="learner@example.com",
        template="invitation",
        data=data,
        idempotency_key="invite-1",
    )
    assert first["delivery_id"] == second["delivery_id"]
    assert record_provider_event(
        {"id": "mail-event-1", "provider": "test", "type": "bounce", "email": "learner@example.com"}
    )["suppressed"] is True
    suppressed = queue_email(
        tenant_id="tenant-email",
        recipient="learner@example.com",
        template="enrollment",
        data=data,
        idempotency_key="enrollment-1",
    )
    assert suppressed["status"] == "suppressed"
