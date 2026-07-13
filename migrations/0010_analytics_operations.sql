BEGIN;

CREATE TABLE IF NOT EXISTS analytics_ingestion_observations (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    observation_id text NOT NULL,
    release_id text NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('accepted', 'duplicate', 'rejected')),
    reason_code text,
    event_key_hash char(64),
    observed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, observation_id),
    FOREIGN KEY (tenant_id, release_id) REFERENCES hosted_releases(tenant_id, release_id)
);

CREATE INDEX IF NOT EXISTS analytics_ingestion_observations_release_idx
    ON analytics_ingestion_observations (tenant_id, release_id, observed_at);

DROP TRIGGER IF EXISTS analytics_ingestion_observations_append_only ON analytics_ingestion_observations;
CREATE TRIGGER analytics_ingestion_observations_append_only
BEFORE UPDATE OR DELETE ON analytics_ingestion_observations
FOR EACH ROW EXECUTE FUNCTION prevent_append_only_mutation();

ALTER TABLE scheduled_reports
    ADD COLUMN IF NOT EXISTS recipient_ciphertexts jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE scheduled_reports
    ADD COLUMN IF NOT EXISTS report_parameters jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS analytics_report_runs (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    run_id text NOT NULL,
    report_id text NOT NULL,
    object_key text,
    sha256 char(64),
    row_count integer NOT NULL DEFAULT 0,
    status text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    PRIMARY KEY (tenant_id, run_id),
    FOREIGN KEY (tenant_id, report_id) REFERENCES scheduled_reports(tenant_id, report_id)
);

INSERT INTO schema_migrations(version)
VALUES ('0010_analytics_operations')
ON CONFLICT (version) DO NOTHING;

COMMIT;
