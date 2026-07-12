BEGIN;

CREATE OR REPLACE FUNCTION prevent_append_only_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('course_mcp.retention_operation', true) = 'on' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

CREATE TABLE IF NOT EXISTS deletion_records (
    deletion_id text PRIMARY KEY,
    tenant_hash char(64) NOT NULL,
    requested_by text NOT NULL,
    export_sha256 char(64) NOT NULL,
    deleted_counts jsonb NOT NULL,
    completed_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations(version)
VALUES ('0006_data_lifecycle')
ON CONFLICT (version) DO NOTHING;

COMMIT;
