import os

import pytest

from course_mcp_server.audit_store import record_audit_event
from course_mcp_server.data_lifecycle import delete_tenant_customer_data, export_tenant
from course_mcp_server.database import database_url
from course_mcp_server.project_store import create_project
from scripts.apply_migrations import apply


pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration only")


def test_tenant_export_precedes_customer_data_deletion_and_retains_audit(tmp_path, monkeypatch):
    apply(database_url())
    monkeypatch.setenv("OBJECT_STORE_LOCAL_ROOT", str(tmp_path / "objects"))
    monkeypatch.delenv("OBJECT_STORE_BUCKET", raising=False)
    tenant_id = "tenant-lifecycle-delete"
    project = create_project(
        tenant_id=tenant_id,
        user_id="owner",
        course_title="Delete Me",
        audience="test",
        language="en",
        compliance_domain=None,
    )
    record_audit_event({"tenant_id": tenant_id, "user_id": "owner", "tool_name": "created"})
    exported = export_tenant(tenant_id=tenant_id)
    assert exported["tables"]["projects"][0]["project_id"] == project["project_id"]
    result = delete_tenant_customer_data(
        tenant_id=tenant_id,
        requested_by="owner",
        confirmation=tenant_id,
        export_sha256=exported["sha256"],
    )
    assert result["deleted_counts"]["projects"] == 1
    retained = export_tenant(tenant_id=tenant_id)
    assert retained["tenant"]["status"] == "deleted"
    assert retained["tables"]["projects"] == []
    assert len(retained["tables"]["audit_events"]) == 1


def test_tenant_deletion_rejects_unverified_export_evidence():
    with pytest.raises(ValueError, match="export evidence"):
        delete_tenant_customer_data(
            tenant_id="tenant-lifecycle-delete",
            requested_by="owner",
            confirmation="tenant-lifecycle-delete",
            export_sha256="x" * 64,
        )
