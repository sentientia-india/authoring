# Best-in-Class Production Roadmap

Status: proposed execution authority  
Created: 2026-07-12  
Scope: Course MCP, Course Studio authoring platform, SCORM delivery, hosted learning, billing, analytics, and public distribution

## 1. Product outcome

Build the best production system for turning source material into polished, editable, standards-compliant training that can be delivered through an LMS or directly on the web.

The product wins when a course owner can:

1. connect the MCP or open Course Studio;
2. import source material or an existing exported course;
3. generate a cited, instructional-quality course;
4. edit the course exactly as learners will see it;
5. validate and export SCORM 1.2 or SCORM 2004 without specialist intervention;
6. publish a hosted link, capture learners, sell access, and inspect results;
7. repeat the workflow safely across a team and many customer accounts.

This is not an LMS replacement. It is an AI-first course production and delivery platform with unusually strong SCORM, source fidelity, round-trip editing, and automation.

## 2. Market position and definition of “best”

The target is not feature-count parity. The target is a better end-to-end outcome for professional course creators, enablement teams, compliance teams, agencies, and developers who need reliable exports.

### 2.1 Required competitive position

| Dimension | Production target | Competitive intent |
|---|---|---|
| Generation | Source-grounded course in under 5 minutes | Faster and more defensible than generic AI drafting |
| Authoring | Real learner player is the editing canvas | Stronger output fidelity than separate editor/preview systems |
| SCORM | 1.2 and 2004 conformance on Moodle, with SCORM Cloud as the final paused cross-check | Primary wedge and trust advantage |
| Hosted delivery | Public, verified, invited, embedded, and paid access | Close the main Mini Course Generator delivery gap |
| Interactivity | Native activities plus optional compatible adapters | Match common course-builder interactions without locking the core to a third party |
| Analytics | Course, learner, attempt, question, and funnel reporting | Actionable evidence, not vanity counts |
| Accessibility | WCAG 2.2 AA authoring checks and player conformance | Enterprise-ready default |
| Team workflow | Revisions, comments, approvals, roles, and audit trail | Agency and enterprise readiness |
| Reliability | Published SLOs, monitored deployments, recoverable data | Production service rather than a demo |
| Developer experience | Working course in under 5 minutes from a copy-paste setup | Best-in-class MCP integration |

### 2.2 Competitive truth gate

Do not claim the product is better than Mini Course Generator overall until all of these are true:

- the editor passes the real-player round-trip suite;
- both SCORM formats pass tracked conformance in two LMS environments;
- hosted links, embeds, access control, analytics, and certificates work in production;
- a first-time user publishes a course in under 10 minutes without help;
- three external course designers approve client-ready output;
- at least one real purchase provisions access without manual work;
- production SLOs are measured for 30 consecutive days.

Before that gate, position the product as better for SCORM-first, MCP-driven, source-grounded course production.

## 3. Non-negotiable product and engineering principles

1. Course Studio remains WYSIWYG: authors edit the actual learner player output.
2. `data/course.json` remains the canonical portable course model.
3. An imported export must be editable and re-exportable without losing tracking, media, interactions, accessibility metadata, or licensing rules.
4. MCP tools remain narrowly allowlisted and never expose shell, arbitrary filesystem, environment, prompt, log, or database access.
5. Third-party open-source components enter through explicit adapters. Their licenses, maintenance state, security history, bundle cost, and data boundaries must be recorded before adoption.
6. Every production feature includes tests, metrics, failure behavior, recovery behavior, documentation, and an owner-facing support path.
7. No roadmap item is “done” because code exists. It is done only when its exit evidence is stored and reproducible.
8. Human acceptance and third-party acceptance cannot be replaced by local tests.

## 4. Current baseline

### 4.1 Existing assets to preserve and build on

- Secure FastMCP server with an explicit tool allowlist.
- Course discovery, ingestion, generation, quality gates, approval, export, and delivery modules.
- SCORM 1.2 and SCORM 2004 export and validation.
- Source-grounded PDF ingestion with page-aware references.
- H5P and Adapt export adapters.
- Course Studio import, actual-player preview, editing, media, interactions, autosave, undo/redo, and re-export work in progress.
- Licensing, rate limiting, billing primitives, provenance, analytics, certificates, and hosted-learning primitives.
- PostgreSQL and Redis service foundations.
- Docker isolation, Caddy TLS profile, CI, security scanning, health checks, smoke tests, and automatic production deployment.
- Local parser and tracked runtime validation for both formats; prior SCORM Cloud evidence is retained.

### 4.2 Critical baseline risks

| Risk | Impact | Required treatment |
|---|---|---|
| Course Studio redesign is uncommitted and replaces legacy static assets | Accidental deployment or merge can lose work or ship an incomplete editor | Stabilize and verify as Phase 0 before unrelated editor changes |
| Moodle completion/score/resume remain unproven with tracked packages | Core value proposition is not externally proven | Phase 1 launch blocker; SCORM Cloud cross-check remains paused until the final acceptance stage |
| Hosted primitives are not a complete multi-tenant product | Data leakage, inconsistent billing, and unreliable analytics risk | Phase 2 architecture gate |
| CI treats dependency-audit failure as non-blocking | Known vulnerable dependencies can reach production | Make high/critical findings blocking with an exception process |
| Deployment replaces the server directory in place | Failed rollout can increase recovery time | Add immutable releases and automatic rollback |
| Public TLS/domain, Stripe, email, LMS, and pilot evidence are incomplete | Production and go-to-market claims cannot be verified | Track as explicit external gates, not hidden TODOs |

## 5. Target architecture

```text
Authors / Developers
        |
        +--> MCP API -------------------------------+
        |                                           |
        +--> Course Studio --> Authoring API         |
                                                    v
                                         Course Application Layer
                                 discovery / ingestion / generation
                                 quality / approval / export / publish
                                                    |
                  +----------------+----------------+----------------+
                  |                |                |                |
             PostgreSQL         Redis/Queue     Object Storage    Event Outbox
          tenant/course/jobs   async work       source/media/zip  reliable events
                  |                |                |                |
                  +----------------+----------------+----------------+
                                                    |
                      +-----------------------------+--------------------+
                      |                             |                    |
               SCORM Exports                 Hosted Learning       Integrations
              Moodle / LMS / Cloud       links / embeds / paywall  Stripe/email/webhooks
                                                    |
                                             Analytics Pipeline
                                       learner / attempt / event / funnel
                                                    |
                                             Admin Operations
                                       metrics / audit / support / recovery
```

### 5.1 Service boundaries

- MCP API: developer and agent orchestration only.
- Authoring API: authenticated browser workflows, media, revisions, previews, imports, and exports.
- Worker: ingestion, LLM generation, media processing, packaging, validation, email, and webhook retries.
- Hosted learner service: read-optimized learner runtime and event collection, isolated from authoring privileges.
- Billing/integration worker: Stripe, email, webhooks, and provisioning.
- Analytics pipeline: append-only events transformed into reporting views.

Start as a modular deployment, not independent microservices. Split processes only where isolation, scaling, or failure behavior requires it.

## 6. Environment and release model

| Environment | Purpose | Data policy | Deployment rule |
|---|---|---|---|
| Local | Development and focused tests | Synthetic fixtures only by default | Developer-controlled |
| CI | Clean build, tests, scans, packaging | Ephemeral | Every pull request and push |
| Staging | Full integrations and acceptance | Synthetic plus approved test accounts | Same artifact intended for production |
| Production | Customer workloads | Encrypted, retained, tenant-scoped | Approval gate plus automatic canary/rollback |

Every release must produce an immutable image tag, software bill of materials, migration identifier, test result, and deployment record. Production deploys must promote the staging-tested artifact rather than rebuild different bytes.

## 7. Execution phases

Phases are sequential at their release gates. Work inside a phase may run in parallel only when it does not share migration or interface risk.

## Phase 0: Preserve and stabilize Course Studio

Objective: turn the current authoring redesign into a protected, tested baseline without changing its product direction.

### Deliverables

- Inventory the current uncommitted editor changes and separate them from unrelated runtime work.
- Make `editor.js`, `editor.css`, and the revised `index.html` the supported UI assets.
- Remove legacy asset references only after the new editor serves successfully.
- Define the editor session model, autosave interval, conflict behavior, undo/redo limits, and session-expiry behavior.
- Preserve actual-player preview and in-place editing.
- Complete editors for course, module, lesson, content block, media, quiz, branching scenario, and final assessment.
- Add loading, empty, importing, saving, saved, invalid, expired, offline, export-failed, and recovery states.
- Add responsive behavior for 1440px, 1024px, 768px, and 390px viewports.
- Add keyboard navigation, focus management, visible focus, labels, error announcements, and minimum touch targets.
- Add revision snapshots before import, destructive structural edits, and export.
- Add import size, file count, path traversal, decompression ratio, MIME, and media validation.

### Required tests

- Import -> edit lesson -> replace media -> edit quiz -> edit branching -> export.
- Exported ZIP passes package validation and quality gates.
- Re-imported ZIP preserves the edited canonical JSON and runtime behavior.
- Autosave recovers after refresh and transient API failure.
- Undo/redo works across text, structure, activity, quiz, and media operations.
- Malicious ZIP cases are rejected without leaving session files.
- Two-tab editing produces a visible conflict instead of silent last-write-wins loss.
- Accessibility automation plus manual keyboard pass.
- Visual snapshots for the four supported viewports.

### Exit gate P0

- All editor tests pass in CI.
- No known P0/P1 editor defect.
- A generated package and an imported package complete the same round-trip suite.
- A user can perform the complete authoring workflow without editing JSON.
- Current authoring changes are committed independently and recoverable.

## Phase 1: Prove delivery conformance

Objective: establish that the exported deliverable works outside this repository.

### Deliverables

- Regenerate SCORM 1.2 and 2004 validation packages using the current runtime.
- Run the same scenarios in a pinned Moodle Docker environment.
- After all other production gates pass, repeat the tracked scenarios in SCORM Cloud as the final cross-check.
- Add a Moodle test harness and documented fixture account.
- Capture parser results, runtime logs, registration state, launch history, screenshots, package hashes, exporter version, and test date.
- Add validation rules for manifest structure, launch files, runtime calls, schema limits, unsafe paths, missing media, and CSP compatibility.
- Add a conformance matrix for SCORM 1.2 and 2004 field mappings.

### Exit gate P1

- Both formats pass the defined Moodle scenarios.
- The paused SCORM Cloud cross-check is completed only at the final acceptance stage.
- Zero unresolved runtime errors.
- Evidence is stored in `docs/` and linked from the release record.
- CI rejects a package that removes any proven tracking capability.

Cannot advance to paid beta if P1 is incomplete.

## Phase 2: Production data, tenancy, jobs, and security

Objective: make the service safe for multiple organizations and recoverable under failure.

### Canonical entities

- tenant, user, membership, role;
- license, subscription, entitlement, usage ledger;
- course, course revision, source, source reference, media asset;
- authoring session, generation job, export job, publish job;
- hosted release, share token, enrollment, learner identity;
- attempt, interaction, completion event, certificate;
- webhook delivery, audit event, support action.

Every persisted row must have an explicit tenant boundary unless it is global configuration. Tenant access tests are mandatory for every repository query.

### Deliverables

- Replace process-local production state with PostgreSQL repositories.
- Add migration tooling, forward migrations, backup-safe migrations, and tested rollback or roll-forward instructions.
- Move large binaries to S3-compatible object storage with signed access and lifecycle rules.
- Use Redis-backed queues for generation, packaging, media, email, and webhook work.
- Define job idempotency keys so retries do not duplicate exports, charges, emails, or hosted releases.
- Add transactional event outbox processing for billing and provisioning.
- Implement role-based access: owner, admin, author, reviewer, analyst, learner, support.
- Add short-lived browser sessions, CSRF protection, secure cookies, origin checks, and revocation.
- Rotate secrets without redeployment and document key ownership.
- Add tenant quotas for storage, generation, exports, hosted learners, and events.
- Add audit trails for permission, export, publish, billing, deletion, and support actions.
- Add deletion, retention, export, and legal-hold behavior.
- Produce a threat model covering MCP, authoring uploads, generated HTML, hosted runtime, webhooks, billing, and support tools.

### Exit gate P2

- Cross-tenant isolation suite passes.
- Backup restore succeeds into a clean staging environment.
- Queue retries and worker restarts do not duplicate side effects.
- High/critical dependency findings block release unless a time-bounded exception exists.
- Threat-model critical findings are resolved.
- A tenant can be exported and deleted according to the documented policy.

## Phase 3: Best-in-class authoring workflow

Objective: make Course Studio faster and more controllable than competing block builders while retaining real-output fidelity.

### Deliverables

- New-course workflow inside Course Studio, not import-only.
- PDF, DOCX, PPTX, text, URL, and YouTube source intake.
- Citation inspector showing the source page/section behind generated claims.
- Course outline approval before full generation.
- Background generation with per-module progress, cancellation, retry, and partial recovery.
- Reusable block library and organization template library.
- Brand kit: logo, color tokens, typography, button style, certificate style, and email style.
- Theme preview across desktop and mobile.
- Drag/drop structure and block ordering with keyboard alternatives.
- Inline AI actions: rewrite, shorten, expand, add example, add assessment, simplify, translate, and regenerate with source constraints.
- Media library with upload, replace, crop metadata, captions, transcripts, rights/source metadata, and usage references.
- Interaction builders for choice, multi-select, flashcards, accordion, matching, fill-in, sorting, hotspots, branching, role-play, timed question, reflection, and interactive video.
- Question bank, randomization, pass rules, retries, feedback, and assessment blueprint.
- Comments, mentions, review assignments, approval status, and immutable published revisions.
- Change comparison between revisions.
- Accessibility checker and export-blocking policy for critical violations.
- Localization workflow with locale inheritance and translation status.

### Exit gate P3

- A first-time author creates, edits, reviews, validates, and publishes a course in under 10 minutes.
- All core actions are available without raw JSON or command-line work.
- Published revision is reproducible from stored inputs and configuration.
- Review and approval history is auditable.
- WCAG 2.2 AA critical checks pass in editor and player.
- Three external designers judge pilot output client-ready without hand-editing the ZIP.

## Phase 4: Hosted delivery, identity, and embeds

Objective: make every course usable without an LMS while keeping SCORM export first-class.

### Deliverables

- Immutable hosted releases separated from draft revisions.
- Share modes: public, unlisted, email-verified, invite-only, tenant-only, and paid.
- Revocable, rotated, scoped share tokens.
- Responsive embed with origin allowlist, resize messaging, and tracking consent.
- Custom domain verification, certificate automation, and safe domain removal.
- Learner identity merge rules across anonymous, email, invitation, and customer-provided IDs.
- Course landing pages, collections, paths, prerequisites, and completion rules.
- Resume across devices.
- Branded transactional email with bounce and complaint handling.
- Certificate issue, verify, revoke, and reissue flows.
- Data-consent and privacy controls appropriate to the configured region.

### Exit gate P4

- All access modes pass authorization tests.
- Revoked links stop working within 60 seconds.
- A hosted release survives author draft changes unchanged.
- Custom domain issuance and renewal work in staging and production.
- Certificate verification works without authenticated access and exposes no private learner data.
- Embed works on the documented browser matrix with no third-party-cookie dependency.

## Phase 5: Analytics and learning evidence

Objective: provide trustworthy operational and learning analytics.

### Event contract

Events must include version, tenant, course release, learner pseudonym, attempt, session, event type, event time, received time, source, and deduplication ID. Raw events are append-only.

### Deliverables

- Events for view, start, progress, interaction, answer, score, complete, abandon, resume, certificate, and conversion.
- Offline buffering and retry with duplicate suppression.
- Course dashboard: starts, completion rate, time, score, drop-off, and question performance.
- Learner timeline and attempt history.
- Collection/path reporting.
- Account-level reporting for customer administrators.
- CSV export and signed scheduled reports.
- Funnel reporting from landing page through purchase and completion.
- Data-quality dashboard for missing, late, rejected, and duplicate events.
- Retention and aggregation policies.
- SCORM analytics remain distinct from hosted analytics but map into a common reporting vocabulary.

### Exit gate P5

- Synthetic event replay produces deterministic reports.
- Duplicate and out-of-order events do not corrupt totals.
- Dashboard totals reconcile with raw events and exports.
- Tenant/report authorization tests pass.
- Defined analytics queries meet p95 latency targets.

## Phase 6: Commerce, licensing, and provisioning

Objective: convert payment into correct access without manual operations.

### Deliverables

- Stripe products, prices, checkout, customer portal, tax configuration boundary, and webhook verification.
- Subscription lifecycle: trial, active, past-due, canceled, paused, renewed, refunded, and disputed.
- Entitlements derived from billing state, not scattered plan checks.
- Idempotent license and tenant provisioning.
- Usage ledger and quota enforcement.
- Paid course checkout and enrollment.
- Receipts and invoices linked from the account area.
- Dunning notifications and grace periods.
- Support tooling for safe entitlement inspection and time-bounded correction.
- Reconciliation job comparing Stripe, entitlements, and usage.

### Exit gate P6

- Test and live low-value purchases provision correct access automatically.
- Replayed webhooks never duplicate provisioning.
- Refund/cancel/past-due scenarios produce documented entitlement transitions.
- Daily reconciliation returns zero unexplained differences.
- No raw payment-card data enters this system.

## Phase 7: Reliability, observability, and operations

Objective: operate the platform with measurable reliability and fast recovery.

### Initial SLOs

| Service indicator | Target |
|---|---|
| MCP and authoring API availability | 99.9% monthly |
| Hosted learner availability | 99.95% monthly |
| API read latency | p95 < 400 ms, p99 < 1 s |
| Authoring save latency | p95 < 750 ms |
| Hosted event acceptance | p95 < 300 ms |
| Standard course generation | p95 < 5 minutes |
| Standard SCORM export | p95 < 60 seconds |
| Recovery point objective | <= 15 minutes |
| Recovery time objective | <= 60 minutes |

### Deliverables

- Structured logs with request, tenant, job, course, and release correlation IDs; never secrets or raw private source content.
- Metrics for traffic, errors, duration, saturation, queues, database, object storage, webhooks, email, generation, export, and analytics quality.
- Distributed traces across API, worker, database, storage, and external calls.
- Error tracking with source maps for Course Studio and the learner player.
- Synthetic checks for login, MCP initialization, generation, export, hosted launch, completion, and purchase.
- Alert routing, severity definitions, escalation, and maintenance windows.
- Runbooks for database failure, Redis failure, storage failure, LLM outage, Stripe outage, email outage, bad deploy, certificate failure, and suspected tenant leak.
- Immutable releases, database migration gate, canary deployment, health verification, and automatic rollback.
- Encrypted backups, restore drills, and quarterly disaster-recovery exercise.
- Capacity model and load tests at 1x, 3x, and 10x projected demand.

### Exit gate P7

- Alerts detect injected failures within the defined time.
- A bad release rolls back without data loss.
- Restore drill meets RPO/RTO.
- Load tests meet SLOs with 30% headroom.
- On-call can resolve the top ten failure scenarios using only the runbooks.

## Phase 8: Developer experience and distribution

Objective: make the MCP and integrations the easiest way to produce a professional course.

### Deliverables

- One copy-paste MCP connection command for each supported client.
- Public HTTPS endpoint with versioned authentication and documented OAuth 2.1 migration.
- Five-minute quickstart with a deterministic sample input.
- Error contract containing code, problem, likely cause, corrective action, and documentation link.
- Versioned tool contracts, changelog, deprecation policy, compatibility window, and migration guides.
- Public MCP registry entry and verified package metadata.
- SDK/examples for direct API use only if real customer demand exists.
- Webhook documentation, signature verification examples, retry policy, and test event sender.
- Status page, security contact, privacy terms, support policy, and service limits.
- Demo gallery containing polished compliance, sales, onboarding, and software-training examples.

### Exit gate P8

- A developer reaches a valid exported course in under 5 minutes from a clean environment.
- Copy-paste examples pass in CI.
- Breaking-change checks protect published schemas.
- Registry installation works from an external machine.
- Support can identify failures from the public error code without private logs.

## Phase 9: Pilot, beta, and general availability

Objective: prove product quality with real users before broad release.

### Pilot set

- Compliance course from a 30+ page regulated source.
- Sales or customer-service scenario course.
- Software onboarding course with screenshots/video.
- At least one agency workflow with review/approval.
- At least one paid hosted course.

### Release stages

| Stage | Entry | Exit |
|---|---|---|
| Internal alpha | P0-P2 complete | Team completes five full workflows; no P0 defects |
| Design-partner alpha | P0-P3 complete | Three client-ready sign-offs and all P1 issues resolved |
| Private beta | P0-P6 complete | 10 tenants, real purchases, no unresolved security criticals |
| Public beta | P0-P8 complete | SLOs measured for 14 days; support/runbooks exercised |
| General availability | All gates complete | 30-day SLO history, DR drill, legal/operational launch checklist signed |

### Stop-ship criteria

- suspected cross-tenant access;
- loss or corruption of canonical course data;
- failed billing reconciliation with unexplained customer impact;
- SCORM regression in a previously proven core field;
- critical upload, generated-content, authentication, or webhook vulnerability;
- inability to restore backups inside the published objective;
- inaccessible primary authoring or learner workflow with no workaround.

## 8. Open-source adoption plan

### 8.1 Adoption gates

No repository is copied or installed until a short decision record contains:

- exact feature gap being solved;
- repository, commit/release, license, and copyright obligations;
- maintenance activity and open security issues;
- transitive dependencies and bundle/runtime cost;
- data transmitted or persisted;
- sandbox and trust boundary;
- adapter interface and removal plan;
- accessibility and browser evidence;
- automated tests proving the integration.

### 8.2 Candidate decisions

| Candidate | Decision | Intended use |
|---|---|---|
| H5P content types/components | Evaluate selectively behind an adapter | Optional advanced interactions and interoperability |
| H5P standalone/player tooling | Spike only | Determine whether packaged H5P can run safely without an H5P server |
| SCORM-H5P wrappers | Reference implementation only until security/license review | Learn packaging and event-mapping patterns |
| Adapt Authoring | Keep separate; export/import boundary only | Compatibility for teams already using Adapt |
| eXeLearning | Reference and external validation only | Moodle/editor workflow comparison |
| Open edX, Chamilo, LAMS | Do not adopt | Full LMS scope conflicts with product focus |

Do not copy competitor presentation, trademarks, proprietary interactions, or undocumented behavior. Match user outcomes through original implementation.

## 9. Test strategy and release evidence

### 9.1 Test layers

| Layer | Required coverage |
|---|---|
| Unit | validation, policy, mapping, calculations, state transitions |
| Contract | MCP schemas, REST schemas, webhooks, event versions, export adapters |
| Integration | PostgreSQL, Redis, object storage, queues, Stripe test mode, email sandbox |
| Security | authorization matrix, tenant isolation, ZIP attacks, XSS/CSP, CSRF, SSRF, webhook replay, secret redaction |
| Round-trip | generate/import/edit/export/re-import plus canonical model comparison |
| Conformance | Moodle tracked scenarios; SCORM Cloud final paused cross-check |
| End-to-end | author, reviewer, learner, buyer, analyst, support workflows |
| Accessibility | automated checks plus manual keyboard/screen-reader sample |
| Visual | editor/player supported viewports and themes |
| Performance | API, save, generation, export, hosted events, dashboards |
| Resilience | dependency outage, retry, restart, duplicate, restore, rollback |

### 9.2 Pull-request gate

- formatting/lint;
- type/schema validation;
- unit and focused integration tests;
- tool allowlist/security tests;
- secret scan, static security scan, dependency audit, and container scan;
- migration validation when schema changes;
- generated artifact diff when exporter/player changes;
- documentation and changelog check for external behavior changes.

### 9.3 Release gate

- full test suite;
- clean container build and SBOM;
- staging migration and smoke test;
- Course Studio critical path;
- SCORM fixture validation;
- hosted learner critical path;
- billing synthetic flow when billing changes;
- canary metrics within thresholds;
- rollback verified or rehearsed for high-risk changes.

## 10. Security and privacy checklist

- Tenant boundary documented at every entry point and repository method.
- Least-privilege service accounts and database roles.
- Encryption in transit and at rest.
- Central secret manager and rotation procedure.
- Upload quarantine, validation, size limits, and safe extraction.
- Generated HTML sanitization and strict content security policy.
- No learner secrets or author source material in logs or analytics payloads.
- Signed and replay-protected webhooks.
- Rate limits by IP, user, tenant, license, learner token, and expensive operation.
- Audit records for privileged support access.
- Dependency and container scanning with enforced severity policy.
- Security headers, CSRF, XSS, SSRF, path traversal, injection, and authorization tests.
- Data inventory, retention schedule, deletion flow, export flow, subprocessors, and incident process.
- Independent penetration test before general availability.

## 11. Accessibility and content-quality checklist

- WCAG 2.2 AA target for Course Studio, landing/account surfaces, and learner runtime.
- Full keyboard workflow and visible focus.
- Screen-reader names, landmarks, status announcements, and error associations.
- Contrast and non-color state indicators.
- Reflow at 200% zoom and 320 CSS pixels.
- Captions/transcripts and media alternatives.
- Alt-text workflow with author confirmation.
- Reduced-motion support.
- Time-limit controls and alternatives.
- Accessible interaction fallbacks.
- Exported course accessibility report stored with each release.
- Citation coverage and unsupported-claim quality gates.
- Assessment blueprint, feedback, difficulty, and answer-integrity checks.

## 12. Operational ownership and workflow

### Definition of ready

A task is ready only when it has:

- user outcome;
- affected interface and data;
- dependencies;
- failure and recovery behavior;
- security/privacy impact;
- acceptance criteria;
- test plan;
- rollout and rollback notes.

### Definition of done

A task is done only when:

- code and migrations are reviewed;
- required tests pass;
- observability exists;
- documentation is updated;
- staging acceptance passes;
- release evidence is linked;
- rollback is understood;
- no unresolved higher-priority defect remains in its blast radius.

### Severity policy

| Severity | Meaning | Response |
|---|---|---|
| P0 | Security breach, cross-tenant exposure, data loss, billing corruption, total outage | Stop ship; immediate response |
| P1 | Core workflow unavailable or incorrect with no acceptable workaround | Fix before release |
| P2 | Important workflow impaired with workaround | Schedule in current milestone |
| P3 | Minor defect or polish issue | Prioritized backlog |

## 13. Ordered implementation backlog

The IDs below are the execution order. A child task can begin early, but its phase cannot pass before all required predecessors pass.

### Launch blockers

- [ ] PROD-001 Protect and inventory the Course Studio redesign.
- [ ] PROD-002 Complete Course Studio functional and failure states.
- [ ] PROD-003 Complete editor security, accessibility, responsive, and conflict behavior.
- [ ] PROD-004 Pass the complete editor round-trip suite.
- [x] PROD-005 Regenerate SCORM validation packages from the corrected runtime. Evidence: CI run `29228239968` archived both packages and SHA-256 validation reports.
- [ ] PROD-006 Run the tracked SCORM Cloud 1.2 and 2004 cross-check last. Status: paused by product decision on 2026-07-13 until every other production gate is complete.
- [x] PROD-007 Build and pass pinned Moodle scenarios. Evidence: `docs/moodle-conformance.md`; CI run `29228239968`, Moodle job `86746998104`.
- [x] PROD-008 Make conformance regression checks release-blocking. Evidence: CI run `29228239968` ran deployment job `86747774750` only after the reusable Moodle job passed.
- [x] PROD-009 Specify canonical tenant/data/event/job models. Evidence: `docs/production-data-contract.md`.
- [x] PROD-010 Persist production state and binaries in PostgreSQL/object storage. Evidence: PostgreSQL migrations/repositories, content-addressed source/media/export objects, immutable hosted-release package objects, `docs/object-storage.md`, and integration tests.
- [x] PROD-011 Add durable queues, idempotency, outbox, retries, dead-lettering, and redrive. Evidence: `migrations/0009_outbox_dead_letters.sql`, `src/course_mcp_server/outbox.py`, `src/course_mcp_server/outbox_worker.py`, and PostgreSQL integration tests.
- [x] PROD-012 Pass tenant isolation, backup restore, and threat-model gates. Evidence: tenant-negative PostgreSQL tests cover project, job, audit, billing, hosted access/revocation, communication delivery, analytics, and outbox redrive; the CI backup/clean-restore drill passes; `docs/security-threat-model.md` records stop-ship findings and controls. CI run `29231241363`.

### Best-in-class authoring

- [x] PROD-101 Add new-course and source-intake workflows to Course Studio. Evidence: `/api/new`, digest-verified workspace source intake, Course Studio source UI, and `tests/test_scorm_editor.py`.
- [x] PROD-102 Add outline approval and cancellable background generation. Evidence: Course Studio requires approved outlines, persists per-module job state, preserves completed modules, supports cooperative cancellation and failed-module retry, and exposes progress controls in Review; covered by `tests/test_scorm_editor.py`.
- [x] PROD-103 Add source/citation inspector. Evidence: Course Studio Sources tab and lesson citation inspector, with sources excluded from learner exports.
- [x] PROD-104 Add template library and brand kit. Evidence: insert palette plus theme, logo, color, typography, button, certificate, and email-style authoring controls in the real-player editor.
- [x] PROD-105 Complete interaction and assessment builders. Evidence: typed interaction inspectors, template insertion, lesson/final question builders, pass rules, retries, randomization, and round-trip tests.
- [x] PROD-106 Add revision history, comparison, comments, roles, and approvals. Evidence: immutable workspace snapshots, optimistic conflict checks, comparison API, collaboration state, Review UI, and tests.
- [x] PROD-107 Add accessibility report and blocking policy. Evidence: `apps/scorm_editor/server.py`, Course Studio Review UI, `tests/test_scorm_editor.py`, and `docs/course-studio-localization-accessibility.md`.
- [x] PROD-108 Add localization workflow. Evidence: persisted locale inheritance, translation overrides/status transitions, Course Studio Review UI, and `tests/test_scorm_editor.py`.
- [ ] PROD-109 Complete three external pilot sign-offs.

### Hosted product

- [ ] PROD-201 Implement immutable hosted releases and share modes.
- [ ] PROD-202 Implement identity, enrollment, resume, and revocation.
- [ ] PROD-203 Implement embeds and custom domains.
- [ ] PROD-204 Implement collections, paths, badges, and certificates.
- [ ] PROD-205 Implement transactional email and deliverability operations.
- [ ] PROD-206 Implement append-only learner event ingestion.
- [ ] PROD-207 Implement course, learner, question, account, and funnel analytics.
- [ ] PROD-208 Implement exports, scheduled reports, retention, and data-quality monitoring.

### Commerce and operations

- [ ] PROD-301 Complete Stripe lifecycle and entitlement model.
- [ ] PROD-302 Complete usage ledger, quotas, paid enrollment, and reconciliation.
- [ ] PROD-303 Add production observability, SLOs, alerts, and status page.
- [ ] PROD-304 Add immutable artifact promotion, canary, and rollback.
- [ ] PROD-305 Complete load, failure, backup, and disaster-recovery exercises.
- [ ] PROD-306 Complete quickstart, registry, compatibility, and migration documentation.
- [ ] PROD-307 Complete security review and independent penetration test.
- [ ] PROD-308 Run private beta, public beta, and GA gates.

## 14. First execution sequence

This is the exact first sequence after approval of this roadmap:

1. Snapshot the dirty worktree and produce a Course Studio change inventory without modifying it.
2. Review the editor server/API and new static assets as one unit.
3. Run focused editor and round-trip tests; classify failures as code, fixture, environment, or missing acceptance coverage.
4. Fix only the editor blast radius and add missing critical tests.
5. Commit the authoring platform as an isolated logical change.
6. Deploy it to staging and run desktop/mobile, keyboard, malicious import, autosave recovery, and export validation.
7. Regenerate both SCORM validation packages.
8. Build the pinned Moodle test environment and run the conformance suite.
9. Update the conformance matrix and make proven behaviors regression gates.
10. Write the multi-tenant data/event/job contract before expanding hosted features.
11. Implement Phase 2 behind migrations and integration tests.
12. Keep SCORM Cloud paused; run it only after every other production gate passes.

## 15. External and human gates

Work that does not need external input continues while these gates wait. These items cannot be truthfully completed without the named dependency:

| Gate | Dependency | Work that continues meanwhile |
|---|---|---|
| SCORM Cloud final cross-check | Paused until all other production gates pass | Every other roadmap item |
| Public TLS/domain | Domain ownership and DNS access | Staging TLS, Caddy tests, domain-verification implementation |
| Live Stripe | Approved Stripe account and live-mode configuration | Test-mode lifecycle, entitlements, reconciliation |
| Production email | Verified sending domain/provider | Email templates, queue, bounce/complaint logic in sandbox |
| Pilot sign-off | Three independent course designers | Pilot generation, QA, feedback capture tooling |
| New-user timing | Independent test participant | Instrumented onboarding and internal rehearsal |
| Penetration test | External security provider or approved tester | Threat modeling, automated security suite, remediation runbook |

## 16. Roadmap governance

- This document becomes the production execution authority after approval.
- `roadmap-next-layer.md` remains historical context, not the active release plan.
- Every backlog item links to evidence before being checked.
- Phase status is one of: not started, in progress, blocked externally, failed gate, passed gate.
- A failed gate reopens the relevant tasks; it is never waived silently.
- Competitive claims are reviewed at P3, P6, P8, and GA using current competitor evidence.
- The roadmap is reviewed after every phase gate and at least monthly during active development.

## 17. Decision audit trail

| # | Decision | Rationale | Rejected alternative |
|---|---|---|---|
| 1 | Keep Course Studio as real-player WYSIWYG | Output fidelity is the strongest differentiated authoring experience | Separate approximate preview canvas |
| 2 | Keep `course.json` canonical | Enables portable round trips and multiple delivery adapters | Editor-specific proprietary state as source of truth |
| 3 | Win the SCORM/MCP niche before claiming overall category leadership | Produces a credible wedge and measurable proof | Feature-count marketing before external evidence |
| 4 | Modular deployment before microservices | Keeps operations understandable while allowing worker/runtime isolation | Premature independent-service expansion |
| 5 | Add hosted delivery and analytics after tenancy/data foundations | Prevents data and billing primitives from becoming unsafe rewrites | Ship public links on process-local primitives |
| 6 | Adopt open source only through documented adapters | Limits license, security, and removal risk | Copying complete third-party authoring platforms into the core |
| 7 | Treat CI, staging evidence, and external acceptance as separate gates | Each catches a different class of failure | Calling local tests production proof |

## GSTACK REVIEW REPORT

Review scope: product strategy, Course Studio UX, architecture, testing, security, reliability, developer experience, competitive readiness, release operations, and external acceptance.

Result: ready for approval as the authoritative production roadmap. Implementation must begin at Phase 0 and may not bypass the P0 or P1 gates.
