import os
import secrets

import pytest

from course_mcp_server.database import database_url
from course_mcp_server.licensing import (
    check_export_quota,
    issue_license,
    record_export,
    resolve_license,
    usage_export,
)
from course_mcp_server.security import SecurityError
from scripts.apply_migrations import apply


pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration only")


def test_product_license_and_export_quota_are_transactional_postgres_state(monkeypatch):
    apply(database_url())
    suffix = secrets.token_hex(4)
    tenant = f"tenant-license-{suffix}"
    key = f"smr_{secrets.token_urlsafe(32)}"
    monkeypatch.setenv("MCP_API_TOKEN", "different-bootstrap-token")
    monkeypatch.delenv("MCP_API_TOKEN_FILE", raising=False)
    issue_license(key, tenant=tenant, tier="pro", monthly_export_quota=1)
    license_ = resolve_license(key)
    assert license_.tenant == tenant
    assert check_export_quota(license_) == {"allowed": True, "used": 0, "quota": 1, "tier": "pro"}
    record_export(license_)
    assert check_export_quota(license_)["allowed"] is False
    with pytest.raises(SecurityError, match="quota exceeded"):
        record_export(license_)
    assert any(row["tenant"] == tenant and row["exports"] == 1 for row in usage_export())
