BEGIN;

CREATE TABLE IF NOT EXISTS hosted_releases (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    release_id text NOT NULL,
    course_id text NOT NULL,
    revision_id text,
    artifact_id text,
    package_object_key text NOT NULL,
    package_sha256 char(64) NOT NULL,
    status text NOT NULL DEFAULT 'published' CHECK (status IN ('published', 'retired')),
    published_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    PRIMARY KEY (tenant_id, release_id),
    UNIQUE (tenant_id, course_id, package_sha256)
);

CREATE TABLE IF NOT EXISTS share_grants (
    tenant_id text NOT NULL,
    grant_id text NOT NULL,
    release_id text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('public', 'unlisted', 'email_verified', 'invite_only', 'tenant_only', 'paid')),
    token_hash char(64) NOT NULL,
    origin_allowlist jsonb NOT NULL DEFAULT '[]'::jsonb,
    expires_at timestamptz,
    revoked_at timestamptz,
    maximum_uses integer CHECK (maximum_uses IS NULL OR maximum_uses > 0),
    use_count integer NOT NULL DEFAULT 0 CHECK (use_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, grant_id),
    FOREIGN KEY (tenant_id, release_id) REFERENCES hosted_releases(tenant_id, release_id),
    UNIQUE (token_hash)
);

CREATE TABLE IF NOT EXISTS learner_identities (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    learner_id text NOT NULL,
    identity_type text NOT NULL CHECK (identity_type IN ('anonymous', 'email', 'invitation', 'external')),
    identity_hash char(64) NOT NULL,
    merged_into_learner_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, learner_id),
    UNIQUE (tenant_id, identity_type, identity_hash),
    FOREIGN KEY (tenant_id, merged_into_learner_id) REFERENCES learner_identities(tenant_id, learner_id)
);

CREATE TABLE IF NOT EXISTS enrollments (
    tenant_id text NOT NULL,
    enrollment_id text NOT NULL,
    learner_id text NOT NULL,
    release_id text NOT NULL,
    entitlement_source text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'expired', 'revoked')),
    enrolled_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    revoked_at timestamptz,
    PRIMARY KEY (tenant_id, enrollment_id),
    FOREIGN KEY (tenant_id, learner_id) REFERENCES learner_identities(tenant_id, learner_id),
    FOREIGN KEY (tenant_id, release_id) REFERENCES hosted_releases(tenant_id, release_id),
    UNIQUE (tenant_id, learner_id, release_id, entitlement_source)
);

CREATE TABLE IF NOT EXISTS learner_attempts (
    tenant_id text NOT NULL,
    attempt_id text NOT NULL,
    enrollment_id text NOT NULL,
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    completion_status text,
    success_status text,
    score numeric(7,3),
    location text,
    suspend_data text,
    session_seconds integer NOT NULL DEFAULT 0 CHECK (session_seconds >= 0),
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    PRIMARY KEY (tenant_id, attempt_id),
    FOREIGN KEY (tenant_id, enrollment_id) REFERENCES enrollments(tenant_id, enrollment_id),
    UNIQUE (tenant_id, enrollment_id, attempt_number)
);

CREATE TABLE IF NOT EXISTS learner_events (
    tenant_id text NOT NULL,
    event_id text NOT NULL,
    release_id text NOT NULL,
    enrollment_id text,
    attempt_id text,
    event_type text NOT NULL,
    event_version integer NOT NULL DEFAULT 1 CHECK (event_version > 0),
    idempotency_key text NOT NULL,
    payload jsonb NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id),
    FOREIGN KEY (tenant_id, release_id) REFERENCES hosted_releases(tenant_id, release_id),
    FOREIGN KEY (tenant_id, enrollment_id) REFERENCES enrollments(tenant_id, enrollment_id),
    FOREIGN KEY (tenant_id, attempt_id) REFERENCES learner_attempts(tenant_id, attempt_id),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS learner_events_release_time_idx
    ON learner_events (tenant_id, release_id, occurred_at);

CREATE TABLE IF NOT EXISTS hosted_entitlements (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    entitlement_id text NOT NULL,
    release_id text NOT NULL,
    subject_hash char(64) NOT NULL,
    access_token_hash char(64) NOT NULL,
    source text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'revoked', 'refunded')),
    effective_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    revoked_at timestamptz,
    PRIMARY KEY (tenant_id, entitlement_id),
    FOREIGN KEY (tenant_id, release_id) REFERENCES hosted_releases(tenant_id, release_id),
    UNIQUE (access_token_hash)
);

CREATE TABLE IF NOT EXISTS captured_leads (
    tenant_id text NOT NULL,
    lead_id text NOT NULL,
    release_id text NOT NULL,
    email_hash char(64) NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, lead_id),
    FOREIGN KEY (tenant_id, release_id) REFERENCES hosted_releases(tenant_id, release_id),
    UNIQUE (tenant_id, release_id, email_hash)
);

DROP TRIGGER IF EXISTS learner_events_append_only ON learner_events;
CREATE TRIGGER learner_events_append_only
BEFORE UPDATE OR DELETE ON learner_events
FOR EACH ROW EXECUTE FUNCTION prevent_append_only_mutation();

INSERT INTO schema_migrations(version)
VALUES ('0002_hosted_learning')
ON CONFLICT (version) DO NOTHING;

COMMIT;
