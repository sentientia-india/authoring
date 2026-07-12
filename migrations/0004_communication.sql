BEGIN;

CREATE TABLE IF NOT EXISTS email_suppressions (
    email_hash char(64) PRIMARY KEY,
    reason text NOT NULL CHECK (reason IN ('bounce', 'complaint', 'manual')),
    provider_event_id text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS email_deliveries (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    delivery_id text NOT NULL,
    template text NOT NULL,
    recipient_hash char(64) NOT NULL,
    recipient_ciphertext text NOT NULL,
    template_data jsonb NOT NULL,
    idempotency_key text NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'sending', 'delivered', 'failed', 'suppressed')),
    provider_message_id text,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    delivered_at timestamptz,
    PRIMARY KEY (tenant_id, delivery_id),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS email_events (
    provider text NOT NULL,
    provider_event_id text NOT NULL,
    event_type text NOT NULL,
    email_hash char(64),
    payload_sha256 char(64) NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, provider_event_id)
);

DROP TRIGGER IF EXISTS email_events_append_only ON email_events;
CREATE TRIGGER email_events_append_only
BEFORE UPDATE OR DELETE ON email_events
FOR EACH ROW EXECUTE FUNCTION prevent_append_only_mutation();

INSERT INTO schema_migrations(version)
VALUES ('0004_communication')
ON CONFLICT (version) DO NOTHING;

COMMIT;
