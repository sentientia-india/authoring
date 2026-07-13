BEGIN;

ALTER TABLE outbox_events
    ADD COLUMN IF NOT EXISTS dead_lettered_at timestamptz;

DROP INDEX IF EXISTS outbox_delivery_idx;
CREATE INDEX IF NOT EXISTS outbox_delivery_idx
    ON outbox_events (available_at, created_at)
    WHERE delivered_at IS NULL AND dead_lettered_at IS NULL;

CREATE TABLE IF NOT EXISTS outbox_dead_letters (
    tenant_id text NOT NULL,
    event_id text NOT NULL,
    event_type text NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    payload jsonb NOT NULL,
    attempt_count integer NOT NULL CHECK (attempt_count > 0),
    error_code text NOT NULL,
    failed_at timestamptz NOT NULL DEFAULT now(),
    redriven_at timestamptz,
    PRIMARY KEY (tenant_id, event_id),
    FOREIGN KEY (tenant_id, event_id) REFERENCES outbox_events(tenant_id, event_id)
);

CREATE INDEX IF NOT EXISTS outbox_dead_letters_pending_idx
    ON outbox_dead_letters (failed_at)
    WHERE redriven_at IS NULL;

INSERT INTO schema_migrations(version)
VALUES ('0009_outbox_dead_letters')
ON CONFLICT (version) DO NOTHING;

COMMIT;
