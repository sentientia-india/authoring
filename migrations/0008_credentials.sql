BEGIN;

CREATE TABLE IF NOT EXISTS badge_definitions (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    badge_id text NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    criteria jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, badge_id)
);

CREATE TABLE IF NOT EXISTS badge_awards (
    tenant_id text NOT NULL,
    award_id text NOT NULL,
    badge_id text NOT NULL,
    learner_id text NOT NULL,
    release_id text NOT NULL,
    evidence jsonb NOT NULL,
    awarded_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    PRIMARY KEY (tenant_id, award_id),
    UNIQUE (tenant_id, badge_id, learner_id, release_id),
    FOREIGN KEY (tenant_id, badge_id) REFERENCES badge_definitions(tenant_id, badge_id),
    FOREIGN KEY (tenant_id, learner_id) REFERENCES learner_identities(tenant_id, learner_id),
    FOREIGN KEY (tenant_id, release_id) REFERENCES hosted_releases(tenant_id, release_id)
);

CREATE TABLE IF NOT EXISTS learner_certificates (
    tenant_id text NOT NULL,
    certificate_id text NOT NULL,
    learner_id text NOT NULL,
    release_id text NOT NULL,
    attempt_id text NOT NULL,
    verification_hash char(64) NOT NULL,
    issued_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    revocation_reason text,
    PRIMARY KEY (tenant_id, certificate_id),
    UNIQUE (tenant_id, attempt_id),
    UNIQUE (verification_hash),
    FOREIGN KEY (tenant_id, learner_id) REFERENCES learner_identities(tenant_id, learner_id),
    FOREIGN KEY (tenant_id, release_id) REFERENCES hosted_releases(tenant_id, release_id),
    FOREIGN KEY (tenant_id, attempt_id) REFERENCES learner_attempts(tenant_id, attempt_id)
);

INSERT INTO schema_migrations(version)
VALUES ('0008_credentials')
ON CONFLICT (version) DO NOTHING;

COMMIT;
