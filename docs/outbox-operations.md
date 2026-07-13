# Outbox consumer and dead-letter operations

Production side effects are delivered from `outbox_events` by an explicit event-handler allowlist in `process_outbox_batch`. Consumers claim rows with a bounded lease and `FOR UPDATE SKIP LOCKED`, so parallel workers cannot deliver the same active lease.

## Failure lifecycle

1. A handler failure releases the lease and schedules a retry without persisting exception messages or secrets.
2. `attempt_count` increments when the event is claimed.
3. At `max_attempts` (default 5), the event is atomically copied to `outbox_dead_letters` and excluded from future claims.
4. Dead letters remain tenant-scoped and are included in tenant export/deletion workflows.

Unsupported event types follow the same bounded failure path. Event handlers are registered explicitly; the worker never dynamically executes event payload content.

## Inspection and redrive

Use the internal functions `list_dead_letters(tenant_id=...)` and `redrive_dead_letter(tenant_id=..., event_id=...)` from an authenticated operational command or admin service. Redrive:

- marks the dead-letter record as redriven;
- clears the event's dead-letter and lease state;
- resets its attempt count and error code;
- makes it immediately claimable.

Do not expose these functions as MCP tools. Before redrive, remediate the provider/configuration fault and verify the original idempotency key still protects the downstream side effect.

## Verification

```powershell
python -m pytest tests/test_outbox_worker.py tests/test_postgres_outbox.py tests/test_database_migrations.py -q
```

The PostgreSQL test proves bounded retries, dead-letter exclusion, tenant isolation, and redrive. CI applies every migration to PostgreSQL before deployment.
