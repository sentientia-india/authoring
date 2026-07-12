BEGIN;

CREATE TABLE IF NOT EXISTS billing_events (
    provider text NOT NULL,
    provider_event_id text NOT NULL,
    event_type text NOT NULL,
    payload_sha256 char(64) NOT NULL,
    tenant_id text,
    processing_result jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, provider_event_id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    subscription_id text NOT NULL,
    provider text NOT NULL,
    provider_subscription_id text NOT NULL,
    provider_customer_id text,
    product_id text,
    price_id text,
    tier text NOT NULL,
    status text NOT NULL CHECK (status IN ('trialing', 'active', 'past_due', 'paused', 'canceled', 'refunded', 'disputed')),
    current_period_start timestamptz,
    current_period_end timestamptz,
    canceled_at timestamptz,
    provider_snapshot_version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, subscription_id),
    UNIQUE (provider, provider_subscription_id)
);

CREATE TABLE IF NOT EXISTS entitlements (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    entitlement_id text NOT NULL,
    capability text NOT NULL,
    limit_value bigint,
    source_type text NOT NULL,
    source_id text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'revoked', 'expired')),
    effective_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    revoked_at timestamptz,
    PRIMARY KEY (tenant_id, entitlement_id),
    UNIQUE (tenant_id, capability, source_type, source_id)
);

CREATE TABLE IF NOT EXISTS usage_entries (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    usage_id text NOT NULL,
    dimension text NOT NULL,
    quantity bigint NOT NULL CHECK (quantity >= 0),
    source_event_id text NOT NULL,
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, usage_id),
    UNIQUE (tenant_id, source_event_id, dimension)
);

CREATE TABLE IF NOT EXISTS reconciliation_runs (
    run_id text PRIMARY KEY,
    provider text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    subscription_count integer NOT NULL DEFAULT 0,
    entitlement_count integer NOT NULL DEFAULT 0,
    unexplained_differences integer NOT NULL DEFAULT 0,
    result jsonb NOT NULL DEFAULT '{}'::jsonb
);

DROP TRIGGER IF EXISTS billing_events_append_only ON billing_events;
CREATE TRIGGER billing_events_append_only
BEFORE UPDATE OR DELETE ON billing_events
FOR EACH ROW EXECUTE FUNCTION prevent_append_only_mutation();

DROP TRIGGER IF EXISTS usage_entries_append_only ON usage_entries;
CREATE TRIGGER usage_entries_append_only
BEFORE UPDATE OR DELETE ON usage_entries
FOR EACH ROW EXECUTE FUNCTION prevent_append_only_mutation();

INSERT INTO schema_migrations(version)
VALUES ('0003_billing')
ON CONFLICT (version) DO NOTHING;

COMMIT;
