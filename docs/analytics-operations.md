# Analytics operations

Hosted learner events are append-only and tenant-scoped. The ingestion boundary accepts the documented learning vocabulary, deduplicates by tenant idempotency key, and records a separate append-only observation for every accepted, duplicate, or rejected submission.

The authenticated quality endpoint reports stored, late, missing-context, duplicate, and rejected counts. A rejected or context-incomplete event fails the quality check and creates durable check evidence. Learner timelines join through tenant-scoped enrollments and never expose learner hashes in response payloads.

Scheduled-report recipients and transactional-email recipients are encrypted with AES-256-GCM and tenant-bound additional authenticated data. Production requires `PII_ENCRYPTION_KEY` to contain a URL-safe base64 encoding of exactly 32 random bytes. Rotation requires decrypt-and-reencrypt migration under a maintenance window; never remove the old key before queued email and report rows are migrated.

The analytics worker claims due schedules with row locks and a bounded lease, writes CSV results to tenant-scoped object storage, records a digest-bearing report run, advances the schedule, and queues one idempotent email per encrypted recipient. The outbox worker has an explicit `email.queued` allowlist, bounded retries, dead-letter transition, and operator redrive. Both run as read-only, non-root, capability-dropped Docker services.
