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


def test_communication_migration_covers_delivery_events_and_suppression():
    migration = (ROOT / "migrations" / "0004_communication.sql").read_text(encoding="utf-8")
    for table in ("email_suppressions", "email_deliveries", "email_events"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "email_events_append_only" in migration


def test_analytics_migration_covers_schedules_and_quality_checks():
    migration = (ROOT / "migrations" / "0005_analytics.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS scheduled_reports" in migration
    assert "CREATE TABLE IF NOT EXISTS analytics_quality_checks" in migration
    assert "scheduled_reports_due_idx" in migration
    operations = (ROOT / "migrations" / "0010_analytics_operations.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS analytics_ingestion_observations" in operations
    assert "CREATE TABLE IF NOT EXISTS analytics_report_runs" in operations
    assert "recipient_ciphertexts" in operations
    assert "analytics_ingestion_observations_append_only" in operations


def test_data_lifecycle_migration_adds_controlled_retention_override_and_evidence():
    migration = (ROOT / "migrations" / "0006_data_lifecycle.sql").read_text(encoding="utf-8")
    assert "course_mcp.retention_operation" in migration
    assert "CREATE TABLE IF NOT EXISTS deletion_records" in migration


def test_outbox_dead_letter_migration_is_tenant_scoped_and_redrivable():
    migration = (ROOT / "migrations" / "0009_outbox_dead_letters.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS outbox_dead_letters" in migration
    assert "PRIMARY KEY (tenant_id, event_id)" in migration
    assert "dead_lettered_at IS NULL" in migration
    assert "redriven_at" in migration


def test_commerce_security_migration_persists_licenses_and_encrypts_email_payloads():
    migration = (ROOT / "migrations" / "0011_commerce_security.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS product_licenses" in migration
    assert "template_data_ciphertext" in migration
    assert "UNIQUE (key_hash)" in migration


def test_hosted_catalog_migration_adds_domains_collections_and_paths():
    migration = (ROOT / "migrations" / "0007_hosted_catalog.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS custom_domains" in migration
    assert "CREATE TABLE IF NOT EXISTS learning_collections" in migration
    assert "CREATE TABLE IF NOT EXISTS learning_collection_items" in migration
    assert "prerequisite_release_id" in migration


def test_credentials_migration_adds_persistent_badges_and_certificates():
    migration = (ROOT / "migrations" / "0008_credentials.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS badge_definitions" in migration
    assert "CREATE TABLE IF NOT EXISTS badge_awards" in migration
    assert "CREATE TABLE IF NOT EXISTS learner_certificates" in migration
    assert "verification_hash" in migration
