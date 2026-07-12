BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id text PRIMARY KEY,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0)
);

CREATE TABLE IF NOT EXISTS projects (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    project_id text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    PRIMARY KEY (tenant_id, project_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    job_id text NOT NULL,
    job_type text NOT NULL,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'completed')),
    idempotency_key text,
    payload jsonb NOT NULL,
    lease_until timestamptz,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    PRIMARY KEY (tenant_id, job_id),
    UNIQUE (tenant_id, job_type, idempotency_key)
);

CREATE TABLE IF NOT EXISTS job_attempts (
    tenant_id text NOT NULL,
    attempt_id text NOT NULL,
    job_id text NOT NULL,
    worker_id text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    outcome text CHECK (outcome IN ('succeeded', 'failed', 'cancelled')),
    error_code text,
    diagnostics jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (tenant_id, attempt_id),
    FOREIGN KEY (tenant_id, job_id) REFERENCES jobs(tenant_id, job_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    artifact_id text NOT NULL,
    project_id text NOT NULL,
    artifact_type text NOT NULL,
    object_key text NOT NULL,
    sha256 char(64) NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    media_type text NOT NULL,
    exporter_version text,
    validation_status text NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    PRIMARY KEY (tenant_id, artifact_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id),
    UNIQUE (tenant_id, object_key)
);

CREATE TABLE IF NOT EXISTS outbox_events (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    event_id text NOT NULL,
    event_type text NOT NULL,
    event_version integer NOT NULL CHECK (event_version > 0),
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    sequence integer NOT NULL CHECK (sequence > 0),
    idempotency_key text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    available_at timestamptz NOT NULL DEFAULT now(),
    leased_until timestamptz,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    delivered_at timestamptz,
    last_error_code text,
    PRIMARY KEY (tenant_id, event_id),
    UNIQUE (tenant_id, aggregate_type, aggregate_id, sequence),
    UNIQUE (tenant_id, event_type, idempotency_key)
);

CREATE INDEX IF NOT EXISTS outbox_delivery_idx
    ON outbox_events (available_at, created_at)
    WHERE delivered_at IS NULL;

CREATE TABLE IF NOT EXISTS audit_events (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    audit_id text NOT NULL,
    actor_id text NOT NULL,
    action text NOT NULL,
    target_type text,
    target_id text,
    result text NOT NULL,
    request_id text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, audit_id)
);

CREATE OR REPLACE FUNCTION prevent_append_only_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events;
CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION prevent_append_only_mutation();

INSERT INTO schema_migrations(version)
VALUES ('0001_production_core')
ON CONFLICT (version) DO NOTHING;

COMMIT;
