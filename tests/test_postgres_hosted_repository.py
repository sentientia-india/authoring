import os
import secrets
from zipfile import ZipFile

import pytest

from course_mcp_server.database import database_url
from course_mcp_server.hosted_repository import (
    append_event,
    capture_lead,
    create_grant,
    create_release,
    dashboard,
    grant_entitlement,
    has_entitlement,
    resolve_grant,
)
from course_mcp_server.hosted_learning import (
    course_dashboard,
    create_share,
    grant_paid_access,
    record_learner_event,
    resolve_share_file,
)
from scripts.apply_migrations import apply


pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration only")


def test_hosted_repository_release_access_events_and_tenant_boundaries():
    apply(database_url())
    release = create_release(
        tenant_id="tenant-hosted",
        course_id="course_1",
        release_id="release_1",
        object_key="tenants/tenant-hosted/releases/release_1/course.zip",
        package_sha256="a" * 64,
    )
    token = secrets.token_urlsafe(24)
    grant = create_grant(tenant_id="tenant-hosted", release_id=release["release_id"], token=token, mode="paid")
    assert resolve_grant(token)["grant_id"] == grant["grant_id"]
    assert resolve_grant("missing-token-that-is-long-enough") is None

    access_token = secrets.token_urlsafe(32)
    grant_entitlement(
        tenant_id="tenant-hosted",
        release_id=release["release_id"],
        purchaser="buyer@example.com",
        access_token=access_token,
    )
    assert has_entitlement(tenant_id="tenant-hosted", release_id=release["release_id"], access_token=access_token)
    assert not has_entitlement(tenant_id="tenant-other", release_id=release["release_id"], access_token=access_token)

    for event_type, payload in (
        ("attempt", {}),
        ("score", {"score": 88}),
        ("completion", {}),
    ):
        append_event(
            tenant_id="tenant-hosted",
            release_id=release["release_id"],
            event_type=event_type,
            learner_hash="learner-hash",
            payload=payload,
        )
    assert dashboard(tenant_id="tenant-hosted", release_id=release["release_id"]) == {
        "learners": 1,
        "completions": 1,
        "attempts": 1,
        "average_score": 88.0,
    }
    assert capture_lead(
        tenant_id="tenant-hosted", release_id=release["release_id"], email="buyer@example.com"
    )["email_hash"]


def test_public_hosted_api_uses_postgres_and_object_store(tmp_path, monkeypatch):
    apply(database_url())
    monkeypatch.setenv("HOSTED_COURSE_ROOT", str(tmp_path / "hosted"))
    monkeypatch.setenv("OBJECT_STORE_LOCAL_ROOT", str(tmp_path / "objects"))
    monkeypatch.delenv("OBJECT_STORE_BUCKET", raising=False)
    package = tmp_path / "sellable.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr("index.html", "<h1>Sellable</h1>")

    share = create_share(package, tenant="tenant-hosted-api", course_id="course_sell", paid=True)
    access = grant_paid_access(share["share_token"], "buyer@example.com")
    assert resolve_share_file(share["share_token"], "index.html", access["access_token"]).is_file()
    record_learner_event(
        share["share_token"],
        {"type": "attempt", "learner_id": "buyer", "idempotency_key": "attempt-1"},
    )
    record_learner_event(
        share["share_token"],
        {"type": "score", "score": 91, "learner_id": "buyer", "idempotency_key": "score-1"},
    )
    record_learner_event(
        share["share_token"],
        {"type": "completion", "learner_id": "buyer", "idempotency_key": "completion-1"},
    )
    assert course_dashboard(share["share_token"])["average_score"] == 91.0
    assert list((tmp_path / "objects").rglob("sellable.zip"))
