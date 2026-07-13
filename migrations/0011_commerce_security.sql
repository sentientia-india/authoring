BEGIN;

ALTER TABLE email_deliveries
    ADD COLUMN IF NOT EXISTS template_data_ciphertext text;

CREATE TABLE IF NOT EXISTS product_licenses (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    license_id text NOT NULL,
    key_hash char(64) NOT NULL,
    tier text NOT NULL CHECK (tier IN ('free', 'pro', 'white_label')),
    monthly_export_quota integer CHECK (monthly_export_quota IS NULL OR monthly_export_quota >= 0),
    expires_at timestamptz,
    disabled_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, license_id),
    UNIQUE (tenant_id),
    UNIQUE (key_hash)
);

INSERT INTO schema_migrations(version)
VALUES ('0011_commerce_security')
ON CONFLICT (version) DO NOTHING;

COMMIT;
