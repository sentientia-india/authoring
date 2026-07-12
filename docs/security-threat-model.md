# Security threat model

Version: 1  
Reviewed: 2026-07-13  
Scope: MCP API, Course Studio, uploads, generation, exports, hosted learning, billing, email, analytics, support, deployment, and dependencies

## Assets and trust boundaries

Protected assets are tenant course content, source documents, learner identity and progress, billing state, entitlements, credentials, signing keys, email addresses, audit evidence, generated packages, and production availability.

Trust boundaries:

1. untrusted MCP/browser clients to authenticated API routes;
2. uploaded archives/documents to extraction and authoring workspaces;
3. generated course HTML/JavaScript to hosted learner browsers;
4. API processes to PostgreSQL, Redis, and object storage;
5. Stripe/email webhooks to billing and communication state;
6. CI artifacts to the production release host;
7. support operators to tenant data;
8. third-party model, payment, email, and LMS providers.

## Threats and required controls

| Boundary | Threat | Required controls | Evidence |
|---|---|---|---|
| MCP/API | tool escalation, tenant spoofing, credential replay | explicit allowlist, license-derived tenant, bearer auth, rate limits, redacted errors | tool/security tests |
| Course Studio upload | ZIP slip, symlink, compression bomb, oversized archive, stored XSS | path/file/ratio/size limits, symlink rejection, generated shell constraints, CSP | editor security tests |
| Hosted content | token guessing, unauthorized paid access, cross-tenant analytics, malicious package script | hashed scoped grants, entitlement check, tenant predicates, immutable release, isolated origin/CSP | hosted PostgreSQL tests |
| PostgreSQL | missing tenant predicate, injection, destructive migration | parameterized SQL, compound tenant keys/FKs, migration CI, backup/restore drill | integration tests |
| Redis/jobs | duplicate side effects, job loss, silent fallback | idempotency markers, durable queue, production fail-closed, outbox leases | queue/outbox tests |
| Object storage | key traversal, public bucket, content tampering | tenant-prefixed validated keys, private network, SHA-256 metadata | object-store tests |
| Stripe | forged/replayed webhook, state regression, duplicate provisioning | HMAC/timestamp verification, event primary key, snapshot ordering, reconciliation | billing tests |
| Email | spoofed provider event, repeated delivery, mail to bounced/complaining recipient | webhook secret, idempotency, suppression list, durable state | communication tests |
| Analytics | cross-tenant query, PII leakage, mutable events | tenant parameters, hashed learner/email identity, append-only events | analytics tests |
| CI/deploy | artifact replacement, partial deploy, secret leakage, failed rollback | SHA release directory, health promotion, previous-release trap, secret files, scans | workflow tests |
| Support | untracked privileged access | separate time-bounded support interface, reason/ticket, immutable audit | required before support tooling |
| Dependencies | compromised/vulnerable library or container | blocking audit, static scan, pinned critical test images, SBOM/container scan | CI gates |

## STRIDE review

- Spoofing: bearer/license authentication, hashed share/access tokens, webhook signatures.
- Tampering: SHA-256 package/object/backup evidence, immutable releases/events, signed export provenance.
- Repudiation: tenant/actor/request audit records and append-only external-event records.
- Information disclosure: tenant-scoped repositories, hashed learner/email identifiers, no secret/prompt/source logging.
- Denial of service: upload limits, rate limits, queue isolation, timeouts, dependency health and alerts.
- Elevation of privilege: role boundaries, no shell/filesystem/database MCP tools, separate hosted/admin routes.

## Stop-ship findings

The following conditions stop release immediately:

- suspected cross-tenant access or missing tenant predicate;
- canonical course, learner, billing, or audit data loss/corruption;
- unsigned/forged billing or email webhook acceptance;
- ZIP traversal, symlink, compression bomb, generated-content XSS, SSRF, or authentication bypass;
- unexplained reconciliation differences;
- failed backup integrity/restore drill;
- failure to roll back an unhealthy candidate;
- critical dependency/container vulnerability without an approved time-bounded exception.

## Remaining independent validation

An independent penetration test must cover authentication/authorization, tenant isolation, archive/document ingestion, hosted generated content, browser/session security, webhook replay, billing access, object storage, and support boundaries. Findings rated critical or high block commercial launch.
