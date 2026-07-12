import os

import pytest

from course_mcp_server.audit_store import list_audit_events, record_audit_event
from course_mcp_server.database import database_url
from course_mcp_server.job_store import get_job_status, record_job
from course_mcp_server.project_store import create_project, get_project
from scripts.apply_migrations import apply


pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration only")


def test_postgres_repositories_enforce_tenant_boundaries():
    assert database_url()
    apply(database_url())

    project = create_project(
        tenant_id="tenant-pg-a",
        user_id="author-a",
        course_title="Postgres Safety",
        audience="operators",
        language="en",
        compliance_domain=None,
    )
    assert get_project(tenant_id="tenant-pg-a", project_id=project["project_id"])
    assert get_project(tenant_id="tenant-pg-b", project_id=project["project_id"]) is None

    record_job(
        job_id="job_postgres_1",
        tenant_id="tenant-pg-a",
        user_id="author-a",
        tool_name="generate_course_blueprint",
        status="completed",
        message="complete",
    )
    assert get_job_status(job_id="job_postgres_1", tenant_id="tenant-pg-a")["status"] == "completed"
    assert get_job_status(job_id="job_postgres_1", tenant_id="tenant-pg-b")["status"] == "not_found"

    record_audit_event({"tenant_id": "tenant-pg-a", "user_id": "author-a", "tool_name": "test"})
    assert len(list_audit_events("tenant-pg-a")) == 1
    assert list_audit_events("tenant-pg-b") == []
