# Production incident runbooks

For every incident: name an incident lead, record the UTC start time and current
release SHA, preserve logs/evidence, communicate impact, and prefer a reversible
containment action. Never paste secrets, source documents, or learner PII into
an incident channel.

| Scenario | Detect | Contain and recover | Verify |
|---|---|---|---|
| Database unavailable | `/health` is 503 and database metric is 0 | stop writes, verify host/storage, fail over or restore the last verified backup | migrations present, tenant probes and smoke tests pass |
| Redis unavailable | dependency metric is 0 | restart Redis; API remains fail-closed for shared rate state | health ready and rate-limit probe passes |
| Object storage unavailable | artifact/report failures and queue growth | pause exports/reports, restore endpoint or credentials, redrive durable work | digest-matched download succeeds |
| LLM/provider outage | generation failures/latency | stop new generation claims, preserve partial jobs, switch approved provider or wait | retry a synthetic module and inspect redacted result |
| Stripe outage | webhook retries or reconciliation gap | keep persisted entitlements unchanged, queue retries, do not hand-edit billing state | signed replay is idempotent and reconciliation is clean |
| Email outage | delivery retries/dead letters | pause consumer if provider rejects globally, repair provider, redrive by idempotency key | sandbox delivery and provider event succeed |
| Bad deploy | candidate health/smoke/load gate fails | automatic trap restarts previous SHA; otherwise run documented manual rollback | current symlink, health, smoke and schema compatibility pass |
| Certificate/custom domain failure | TLS or domain authorization probe fails | disable only the affected domain, validate DNS/ownership, then retry issuance | HTTPS launch serves the expected release |
| Suspected tenant leak | any cross-tenant evidence | stop affected public paths, preserve audit evidence, rotate exposed tokens, notify security lead | negative isolation suite passes before reopening |
| Backup/restore failure | stale backup or drill exceeds RPO/RTO | repair backup destination/credentials, create fresh backup, restore into isolated database | digest, row counts, migrations and RPO/RTO evidence pass |

Severity is critical for data isolation, total unavailability, billing access
errors, failed restore, or corrupted canonical course data. Everything else is
warning unless customer impact or duration crosses the published SLO policy.

## Exercise gate

`python scripts/runbook_exercise.py --release <sha>` performs the
non-destructive release tabletop for a bad deployment, email-provider outage,
and suspected tenant leak. It verifies incident ownership, UTC evidence,
reversible containment, customer communication, secret/PII handling, and
recovery checks. CI blocks release if the runbook no longer contains the
required response controls. The initial execution record is stored at
`docs/evidence/support-runbook-2026-07-13.json`; live incidents and quarterly
disaster-recovery drills remain separate operational evidence.
