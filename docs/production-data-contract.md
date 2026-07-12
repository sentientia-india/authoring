# Production data, event, and job contract

Status: authoritative for Phase 2 implementation  
Version: 1  
Updated: 2026-07-12

This contract defines ownership, identifiers, tenancy, lifecycle, and idempotency before production persistence is expanded. Implementations may add columns, but may not weaken these boundaries without a versioned migration and security review.

## Global rules

1. Every customer-owned row carries a non-null `tenant_id`; global configuration is stored separately.
2. Primary identifiers are opaque UUIDv7 values. Human slugs are mutable labels, never authorization keys.
3. Repository methods require `tenant_id` as an explicit argument and include it in every lookup, update, and delete predicate.
4. Cross-tenant joins are prohibited except inside audited support operations with an explicit reason and actor.
5. Mutable entities carry `created_at`, `updated_at`, and an optimistic `version` integer.
6. Published releases, learner events, audit events, usage entries, and billing events are append-only.
7. User deletion pseudonymizes retained financial/audit evidence and removes personal content according to retention policy.
8. Binary payloads live in object storage. Database rows hold metadata, digest, size, media type, and object key.
9. External and retryable operations require a tenant-scoped idempotency key.
10. Timestamps are UTC and stored with timezone information.

## Identity and tenancy

| Entity | Required identity | Ownership and invariants |
|---|---|---|
| `tenant` | `tenant_id` | Root customer boundary; lifecycle is active, suspended, or deleted. |
| `user` | `user_id` | Global login identity; normalized email is unique where email login is enabled. |
| `membership` | `(tenant_id, user_id)` | Role is owner, admin, author, reviewer, analyst, learner, or support; tenant must always retain one owner. |
| `browser_session` | `session_id` | User and active tenant are fixed at issue time; short expiry; revocable; token stored hashed. |
| `api_credential` | `credential_id` | Tenant-scoped except bootstrap administration; secret stored hashed; carries scopes and expiry. |

## Authoring and content

| Entity | Required identity | Ownership and invariants |
|---|---|---|
| `course` | `(tenant_id, course_id)` | Stable logical course; points to draft and published revision IDs. |
| `course_revision` | `(tenant_id, revision_id)` | Canonical `course.json`, schema version, parent revision, author, digest, and immutable flag. Published revisions are immutable. |
| `source` | `(tenant_id, source_id)` | Original filename/URL, content digest, extraction status, object key, and retention class. |
| `source_reference` | `(tenant_id, reference_id)` | Revision-to-source citation with page/section locator and excerpt digest. |
| `media_asset` | `(tenant_id, asset_id)` | Object key, SHA-256, MIME, size, dimensions/duration, rights/source metadata, alt text, transcript state. |
| `authoring_session` | `(tenant_id, session_id)` | Revision base, current version, expiry, last save, and conflict status. Never grants access by possession alone. |
| `review` | `(tenant_id, review_id)` | Revision, assignee, state, decision, and timestamps. |
| `comment` | `(tenant_id, comment_id)` | Revision and stable block target; edit history retained. |

## Work and artifact lifecycle

| Entity | Required identity | Ownership and invariants |
|---|---|---|
| `job` | `(tenant_id, job_id)` | Type, state, attempt, progress, input digest, idempotency key, cancellation time, error code, result references. |
| `job_attempt` | `(tenant_id, attempt_id)` | Append-only execution record with worker, lease, started/finished times, outcome, and redacted diagnostics. |
| `artifact` | `(tenant_id, artifact_id)` | Kind, revision, object key, digest, size, exporter version, validation status, and expiry. |
| `export_job` | `job_id` | References immutable input revision; identical successful idempotency key returns the prior artifact. |
| `publish_job` | `job_id` | References artifact and release target; retry may not create a duplicate release. |

Job states are `queued -> running -> succeeded|failed|cancelled`. A failed retry creates a new `job_attempt`, not a duplicate job. Workers lease jobs for bounded periods; expired leases can be reclaimed. Cancellation is cooperative and blocks publishing of late results.

## Hosted learning

| Entity | Required identity | Ownership and invariants |
|---|---|---|
| `hosted_release` | `(tenant_id, release_id)` | Immutable revision/artifact binding; publish and retirement timestamps. |
| `share_grant` | `(tenant_id, grant_id)` | Release, mode, hashed token, scopes, origin allowlist, expiry, revocation, and maximum uses. |
| `learner_identity` | `(tenant_id, learner_id)` | Anonymous, email, invitation, or external identity; merge operations are audited. |
| `enrollment` | `(tenant_id, enrollment_id)` | Learner, release/course, entitlement source, state, start/expiry. Unique active enrollment per learner/course/source. |
| `attempt` | `(tenant_id, attempt_id)` | Enrollment, release, attempt number, completion/success, score, location, suspend data, and times. |
| `interaction_event` | `(tenant_id, event_id)` | Append-only attempt event; question/activity identity, response, result, latency, and event version. |
| `certificate` | `(tenant_id, certificate_id)` | Attempt, issue/revoke/reissue chain, verification digest, and template version. |

## Billing, licensing, and usage

| Entity | Required identity | Ownership and invariants |
|---|---|---|
| `subscription` | `(tenant_id, subscription_id)` | Provider IDs, product/price, state, period, cancellation, and provider snapshot version. |
| `entitlement` | `(tenant_id, entitlement_id)` | Capability, limits, source, effective interval, and revocation. Derived from verified billing/admin events. |
| `usage_entry` | `(tenant_id, usage_id)` | Append-only dimension, quantity, occurred time, source event, and idempotency key. |
| `billing_event` | `(provider, provider_event_id)` | Append-only verified webhook envelope digest and processing state. Provider ID is globally unique. |
| `reconciliation_run` | `run_id` | Compared provider, entitlements, and usage positions; unexplained differences block release. |

No request handler trusts client-provided plan/tier values. Authorization uses active entitlements read through the tenant boundary.

## Reliable event outbox

Each state change that requires an external side effect writes the domain row and `outbox_event` in one database transaction.

Required fields:

- `event_id`, `tenant_id`, `event_type`, `event_version`;
- `aggregate_type`, `aggregate_id`, `sequence`;
- `payload` containing identifiers only where possible;
- `idempotency_key`, `created_at`, `available_at`;
- `attempt_count`, `leased_until`, `delivered_at`, `last_error_code`.

Consumers deduplicate by `(consumer, event_id)`. Delivery is at least once. Ordering is guaranteed only within one aggregate sequence. Personally identifying or source content is not copied into events unless the consumer contract requires it.

## Audit and support

`audit_event` is append-only and contains tenant, actor, action, target, result, request correlation ID, source IP classification, timestamp, and structured redacted metadata. It never stores credentials, raw prompts, private source bodies, database queries, or filesystem paths.

Support access requires a time-bounded grant with ticket/reason, named operator, tenant, capabilities, expiry, and immutable audit events for every read or mutation.

## Mandatory database constraints

- Foreign keys include `tenant_id` wherever both sides are tenant-owned.
- Unique keys are tenant-scoped unless explicitly global.
- Published/append-only tables reject updates through application permissions.
- Object digest is SHA-256 and object keys cannot contain user-controlled path traversal.
- Idempotency uniqueness: `(tenant_id, operation, idempotency_key)`.
- Attempt uniqueness: `(tenant_id, enrollment_id, attempt_number)`.
- Outbox aggregate ordering: `(tenant_id, aggregate_type, aggregate_id, sequence)`.
- Usage deduplication: `(tenant_id, source_event_id, dimension)`.

## Repository authorization contract

All tenant repositories implement methods shaped like:

```python
get(*, tenant_id: str, entity_id: str)
list(*, tenant_id: str, ...filters)
create(*, tenant_id: str, ...)
update(*, tenant_id: str, entity_id: str, expected_version: int, ...)
delete(*, tenant_id: str, entity_id: str)
```

An identifier without `tenant_id` is insufficient. “Not found” is returned for both missing and foreign-tenant entities to avoid existence disclosure. Administrative cross-tenant access uses a separate audited interface and cannot be reached through MCP tools.

## Migration order

1. tenant, user, membership, credential/session;
2. course, revision, source/reference, media, authoring/review;
3. job, attempt, artifact, outbox, consumer receipt;
4. hosted release, grant, learner, enrollment, attempt, interaction, certificate;
5. subscription, billing event, entitlement, usage, reconciliation;
6. audit and support grants;
7. migrate JSON records tenant-by-tenant with counts and digests;
8. run dual-read comparison, switch writes, then retire JSON only after backup and rollback evidence.

## Acceptance evidence for PROD-009

- Entity ownership and lifecycle are defined above.
- Tenant keys and repository rules are explicit.
- Job retry, cancellation, lease, and idempotency semantics are explicit.
- Event delivery, ordering, versioning, and deduplication are explicit.
- Billing-derived entitlement and usage boundaries are explicit.
- Migration order preserves rollback and comparison paths.
