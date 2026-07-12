from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_data_contract_covers_tenant_and_reliability_boundaries():
    contract = (ROOT / "docs" / "production-data-contract.md").read_text(encoding="utf-8")

    required_terms = (
        "tenant_id",
        "course_revision",
        "authoring_session",
        "job_attempt",
        "idempotency_key",
        "outbox_event",
        "hosted_release",
        "learner_identity",
        "interaction_event",
        "billing_event",
        "usage_entry",
        "reconciliation_run",
        "expected_version",
    )
    for term in required_terms:
        assert term in contract

    assert "An identifier without `tenant_id` is insufficient" in contract
    assert "Administrative cross-tenant access uses a separate audited interface" in contract
