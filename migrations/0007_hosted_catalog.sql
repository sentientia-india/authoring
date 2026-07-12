BEGIN;

CREATE TABLE IF NOT EXISTS custom_domains (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    domain_id text NOT NULL,
    hostname text NOT NULL,
    verification_token_hash char(64) NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'active', 'failed', 'removed')),
    release_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    verified_at timestamptz,
    removed_at timestamptz,
    PRIMARY KEY (tenant_id, domain_id),
    UNIQUE (hostname),
    FOREIGN KEY (tenant_id, release_id) REFERENCES hosted_releases(tenant_id, release_id)
);

CREATE TABLE IF NOT EXISTS learning_collections (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    collection_id text NOT NULL,
    title text NOT NULL,
    slug text NOT NULL,
    description text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, collection_id),
    UNIQUE (tenant_id, slug)
);

CREATE TABLE IF NOT EXISTS learning_collection_items (
    tenant_id text NOT NULL,
    collection_id text NOT NULL,
    release_id text NOT NULL,
    position integer NOT NULL CHECK (position > 0),
    prerequisite_release_id text,
    required boolean NOT NULL DEFAULT true,
    PRIMARY KEY (tenant_id, collection_id, release_id),
    UNIQUE (tenant_id, collection_id, position),
    FOREIGN KEY (tenant_id, collection_id) REFERENCES learning_collections(tenant_id, collection_id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, release_id) REFERENCES hosted_releases(tenant_id, release_id),
    FOREIGN KEY (tenant_id, prerequisite_release_id) REFERENCES hosted_releases(tenant_id, release_id)
);

INSERT INTO schema_migrations(version)
VALUES ('0007_hosted_catalog')
ON CONFLICT (version) DO NOTHING;

COMMIT;
