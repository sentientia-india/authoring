import os

import pytest

from course_mcp_server.communication import CommunicationError, deliver_email, queue_email, record_provider_event
from course_mcp_server.database import connection, database_url
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
    with connection() as active:
        stored = active.execute(
            "SELECT recipient_ciphertext, template_data, template_data_ciphertext FROM email_deliveries WHERE tenant_id = %s AND delivery_id = %s",
            ("tenant-email", first["delivery_id"]),
        ).fetchone()
    assert stored["recipient_ciphertext"].startswith("v1:")
    assert "learner@example.com" not in stored["recipient_ciphertext"]
    assert stored["template_data"] == {"encrypted": True}
    assert stored["template_data_ciphertext"].startswith("v1:")
    assert "https://example.com/course" not in stored["template_data_ciphertext"]
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


def test_email_delivery_cannot_cross_tenant_boundary():
    apply(database_url())
    queued = queue_email(
        tenant_id="tenant-email-owner",
        recipient="owner@example.com",
        template="invitation",
        data={"course_title": "Safety", "action_url": "https://example.com/course"},
        idempotency_key="tenant-boundary",
    )
    with pytest.raises(CommunicationError, match="not sendable"):
        deliver_email(tenant_id="tenant-email-other", delivery_id=queued["delivery_id"])
