BEGIN;

CREATE TABLE IF NOT EXISTS scheduled_reports (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    report_id text NOT NULL,
    report_type text NOT NULL CHECK (report_type IN ('course', 'learner', 'question', 'account', 'funnel')),
    release_id text,
    cadence text NOT NULL CHECK (cadence IN ('daily', 'weekly', 'monthly')),
    recipient_hashes jsonb NOT NULL,
    format text NOT NULL DEFAULT 'csv' CHECK (format IN ('csv', 'json')),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'deleted')),
    next_run_at timestamptz NOT NULL,
    last_run_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, report_id),
    FOREIGN KEY (tenant_id, release_id) REFERENCES hosted_releases(tenant_id, release_id)
);

CREATE INDEX IF NOT EXISTS scheduled_reports_due_idx
    ON scheduled_reports (next_run_at)
    WHERE status = 'active';

CREATE TABLE IF NOT EXISTS analytics_quality_checks (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    check_id text NOT NULL,
    release_id text,
    check_type text NOT NULL,
    status text NOT NULL CHECK (status IN ('passed', 'failed')),
    observed_value numeric,
    expected_value numeric,
    checked_at timestamptz NOT NULL DEFAULT now(),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (tenant_id, check_id),
    FOREIGN KEY (tenant_id, release_id) REFERENCES hosted_releases(tenant_id, release_id)
);

INSERT INTO schema_migrations(version)
VALUES ('0005_analytics')
ON CONFLICT (version) DO NOTHING;

COMMIT;
