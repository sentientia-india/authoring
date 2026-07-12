from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_core_migration_enforces_tenant_and_reliability_constraints():
    migration = (ROOT / "migrations" / "0001_production_core.sql").read_text(encoding="utf-8")

    for table in ("tenants", "projects", "jobs", "job_attempts", "artifacts", "outbox_events", "audit_events"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "PRIMARY KEY (tenant_id, project_id)" in migration
    assert "PRIMARY KEY (tenant_id, job_id)" in migration
    assert "UNIQUE (tenant_id, aggregate_type, aggregate_id, sequence)" in migration
    assert "prevent_append_only_mutation" in migration
    assert "BEGIN;" in migration and "COMMIT;" in migration


def test_migration_runner_uses_sorted_sql_files_and_requires_database_url():
    runner = (ROOT / "scripts" / "apply_migrations.py").read_text(encoding="utf-8")

    assert 'sorted(migrations_dir.glob("*.sql"))' in runner
    assert 'os.getenv("DATABASE_URL")' in runner
    assert "psycopg.connect" in runner


def test_hosted_migration_defines_immutable_releases_access_and_learning_state():
    migration = (ROOT / "migrations" / "0002_hosted_learning.sql").read_text(encoding="utf-8")

    for table in (
        "hosted_releases",
        "share_grants",
        "learner_identities",
        "enrollments",
        "learner_attempts",
        "learner_events",
        "hosted_entitlements",
        "captured_leads",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "learner_events_append_only" in migration
    assert "UNIQUE (tenant_id, enrollment_id, attempt_number)" in migration
    assert "UNIQUE (access_token_hash)" in migration


def test_billing_migration_covers_lifecycle_entitlements_usage_and_reconciliation():
    migration = (ROOT / "migrations" / "0003_billing.sql").read_text(encoding="utf-8")
    for table in ("billing_events", "subscriptions", "entitlements", "usage_entries", "reconciliation_runs"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "billing_events_append_only" in migration
    assert "usage_entries_append_only" in migration
