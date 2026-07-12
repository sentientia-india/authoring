import os
import secrets
from zipfile import ZipFile

import pytest

from course_mcp_server.database import database_url
from course_mcp_server.hosted_repository import (
    append_event,
    capture_lead,
    add_collection_item,
    award_badge,
    create_collection,
    create_badge_definition,
    create_grant,
    create_release,
    dashboard,
    grant_entitlement,
    get_or_create_learner,
    get_collection,
    has_entitlement,
    issue_learner_certificate,
    enroll_learner,
    resolve_grant,
    revoke_enrollment,
    revoke_grant,
    request_custom_domain,
    save_attempt_state,
    verify_custom_domain,
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


def test_identity_enrollment_resume_and_revocation_lifecycle():
    apply(database_url())
    release = create_release(
        tenant_id="tenant-lifecycle",
        course_id="course_lifecycle",
        release_id="release_lifecycle",
        object_key="tenants/tenant-lifecycle/releases/release_lifecycle/course.zip",
        package_sha256="b" * 64,
    )
    learner = get_or_create_learner(
        tenant_id="tenant-lifecycle", identity_type="email", identity="Learner@Example.com"
    )
    same_learner = get_or_create_learner(
        tenant_id="tenant-lifecycle", identity_type="email", identity="learner@example.com"
    )
    assert learner["learner_id"] == same_learner["learner_id"]
    enrollment = enroll_learner(
        tenant_id="tenant-lifecycle",
        learner_id=learner["learner_id"],
        release_id=release["release_id"],
        entitlement_source="invitation",
    )
    first = save_attempt_state(
        tenant_id="tenant-lifecycle",
        enrollment_id=enrollment["enrollment_id"],
        attempt_number=1,
        completion_status="incomplete",
        location="module-1",
        suspend_data='{"block":2}',
        session_seconds=45,
    )
    resumed = save_attempt_state(
        tenant_id="tenant-lifecycle",
        enrollment_id=enrollment["enrollment_id"],
        attempt_number=1,
        completion_status="completed",
        success_status="passed",
        score=100,
        session_seconds=15,
    )
    assert resumed["attempt_id"] == first["attempt_id"]
    assert resumed["location"] == "module-1"
    assert resumed["suspend_data"] == '{"block":2}'
    assert resumed["session_seconds"] == 60
    assert resumed["version"] == 2
    assert revoke_enrollment(tenant_id="tenant-lifecycle", enrollment_id=enrollment["enrollment_id"])

    token = secrets.token_urlsafe(24)
    grant = create_grant(
        tenant_id="tenant-lifecycle", release_id=release["release_id"], token=token, mode="invite_only"
    )
    assert resolve_grant(token)
    assert revoke_grant(tenant_id="tenant-lifecycle", grant_id=grant["grant_id"])
    assert resolve_grant(token) is None


def test_custom_domain_and_learning_collection_are_tenant_scoped():
    apply(database_url())
    tenant = f"tenant-catalog-{secrets.token_hex(4)}"
    release = create_release(
        tenant_id=tenant,
        course_id="course_catalog",
        release_id="release_catalog",
        object_key=f"tenants/{tenant}/releases/release_catalog/course.zip",
        package_sha256="c" * 64,
    )
    requested = request_custom_domain(
        tenant_id=tenant, hostname=f"academy-{secrets.token_hex(4)}.example.com", release_id=release["release_id"]
    )
    verified = verify_custom_domain(
        tenant_id=tenant,
        hostname=requested["hostname"],
        observed_token=requested["dns_record"]["value"],
    )
    assert verified["status"] == "verified"
    collection = create_collection(tenant_id=tenant, title="Customer Academy", slug="customer-academy")
    add_collection_item(
        tenant_id=tenant,
        collection_id=collection["collection_id"],
        release_id=release["release_id"],
        position=1,
    )
    loaded = get_collection(tenant_id=tenant, collection_id=collection["collection_id"])
    assert loaded["items"][0]["release_id"] == release["release_id"]
    assert get_collection(tenant_id="tenant-other", collection_id=collection["collection_id"]) is None


def test_badges_and_certificates_are_persistent_and_idempotent():
    apply(database_url())
    tenant = f"tenant-credentials-{secrets.token_hex(4)}"
    release = create_release(
        tenant_id=tenant,
        course_id="course_credentials",
        release_id="release_credentials",
        object_key=f"tenants/{tenant}/releases/release_credentials/course.zip",
        package_sha256="d" * 64,
    )
    learner = get_or_create_learner(tenant_id=tenant, identity_type="email", identity="credential@example.com")
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
        completion_status="completed",
        success_status="passed",
        score=96,
    )
    create_badge_definition(
        tenant_id=tenant,
        badge_id="badge_mastery",
        name="Course mastery",
        description="Completed with mastery",
        criteria={"minimum_score": 85},
    )
    first_award = award_badge(
        tenant_id=tenant,
        badge_id="badge_mastery",
        learner_id=learner["learner_id"],
        release_id=release["release_id"],
        evidence={"attempt_id": attempt["attempt_id"], "score": 96},
    )
    repeated_award = award_badge(
        tenant_id=tenant,
        badge_id="badge_mastery",
        learner_id=learner["learner_id"],
        release_id=release["release_id"],
        evidence={"attempt_id": attempt["attempt_id"], "score": 96},
    )
    assert repeated_award["award_id"] == first_award["award_id"]
    certificate = issue_learner_certificate(
        tenant_id=tenant,
        learner_id=learner["learner_id"],
        release_id=release["release_id"],
        attempt_id=attempt["attempt_id"],
    )
    repeated = issue_learner_certificate(
        tenant_id=tenant,
        learner_id=learner["learner_id"],
        release_id=release["release_id"],
        attempt_id=attempt["attempt_id"],
    )
    assert repeated["certificate_id"] == certificate["certificate_id"]
    assert len(certificate["verification_hash"]) == 64
