# Next Layer Roadmap

Written 2026-07-11, after the agent-authored pipeline, Level 3.5/4 player, media briefs, 3-question interview, parallel module submission, and licensing shipped (see task-board T-014..T-016). This is the plan for turning a working product into a sellable, defensible one.

Ordering principle: **prove the deliverable → make it editable → make it easy to buy → make it hard to leave.** Each item has an acceptance test; nothing counts as done without it.

## Delivery status — 2026-07-11

- Implemented and locally verified: A3, B1 decision, B2, B3 automated preservation coverage, C1 application/TLS configuration, C2 tutorial/landing/gallery foundations, D1 webhook/license automation, D2 anti-abuse/provenance, and E1–E4 hosted service primitives.
- Requires external acceptance evidence before it can truthfully be marked done: A1 SCORM Cloud and Moodle runtime runs; A2 three pilot-designer sign-offs; C1 public domain/TLS connection; C2 independent new-user timing; C3 registry publication; D1 live Stripe checkout; E1–E4 hosted paying-tier demo runs.
- Local automation cannot substitute for those third-party accounts or human acceptance tests. The repository contains the test harnesses, deployment configuration, and operational instructions needed to execute them once access is supplied.

---

## Track A — Prove the deliverable (first)

**A1. SCORM conformance on real LMSes.**
Upload exported zips (1.2 and 2004) to SCORM Cloud and at least one real LMS (Moodle docker). Fix any runtime findings (completion, score, suspend/resume, interactions). Add a conformance checklist to CI (extend `validate_scorm_package`).
*Done when: a demo course reports completion + score correctly on SCORM Cloud with zero runtime errors.*

**A2. Three real pilot courses.**
Build pilots from real source PDFs in three domains (compliance, sales, software onboarding) using the full 3-question flow. Capture designer feedback; tune quality-gate thresholds against real content instead of fixtures.
*Done when: a pilot designer signs off a course as client-shippable without hand-editing the zip.*

**A3. PDF extraction fidelity.**
The live extractor (`ingestion._extract_pdf`) is regex-over-bytes; the pypdf-based extractor in `source_ingestion.py` exists but is unused. Switch the live path to pypdf with the regex as fallback, add page-anchored `source_refs` so citations point at real pages, and add fidelity tests with real PDFs.
*Done when: a 30-page PDF ingests with per-page chunk references and no mojibake.*

## Track B — Editor layer

**B1. Decide Adapt vs in-house (time-boxed spike, 2 days).**
Resume the parked Adapt Authoring spike on a Docker host (requires MongoDB ≤ 4.4; nvm/Node 18 already proven). Measure the real cost of mapping our `course.json` schema into Adapt's content model, and settle the GPL-3.0 boundary (run as an arm's-length service, never embed code).
*Done when: a written go/no-go with the mapping cost estimate.*

**B2. If no-go: upgrade `apps/scorm_editor` to the new schema.**
It already round-trips `data/course.json`. Add: slide-level preview using the actual game player, media manager (browse/replace `assets/media`), `game_options` toggles, quiz/branching editors, autosave.
*Done when: import demo zip → edit a lesson + swap an image → re-export → zip passes `validate_scorm_package` and the quality gate.*

**B3. Round-trip guarantee (either path).**
Exported zip → editor → re-export must preserve SCORM validity, tracking, and licensing branding rules.
*Done when: CI has a round-trip test.*

## Track C — Distribution and onboarding

**C1. Hosted MCP endpoint.**
Deploy behind TLS reverse proxy with health/metrics; pin the fastmcp version; document the OAuth 2.1 migration path (current: license key as bearer token).
*Done when: a stranger can connect from Claude Code with one `claude mcp add` command and a license key.*

**C2. Ten-minute first course.**
A tutorial doc + demo gallery: connect MCP → answer 3 questions → say "go" → download zip. Include 2–3 polished gallery zips as proof.
*Done when: a new user (not the author) produces a course in under 10 minutes following only the doc.*

**C3. Be findable.**
List in MCP registries/directories; product landing page with the gallery and pricing tiers.
*Done when: the server is installable from a public registry entry.*

## Track D — Monetization hardening

**D1. License lifecycle automation.**
Stripe checkout → webhook → `issue_license` automatically; renewal/expiry warnings surfaced in tool responses; usage export (per-tenant monthly counts) for billing reconciliation.
*Done when: a purchase creates a working key with zero manual steps.*

**D2. Anti-abuse.**
Per-tenant upload storage quotas; per-license rate limits (extend `rate_limit.py` keying); free-tier watermark policy enforced in exporter; signed export stamp (HMAC of course_id + license) embedded in `course.json` for provenance.
*Done when: quota/watermark tests pass and stamps verify.*

## Track E — Hosted phase (after A–D)

The features deferred because they host learner traffic — MCG/Coursebox parity closers:

- **E1. Share links**: static hosting of exported zips behind share tokens — a live course link without an LMS (MCG's headline feature).
- **E2. Learner analytics lite**: optional completion/score beacon from the SCORM runtime when online; per-course dashboard.
- **E3. AI tutor + AI grading**: in-course tutor chat and open-answer grading, BYO-key so inference cost stays on the customer (consistent with the business model).
- **E4. Course selling**: payment-gated share links, lead capture on completion.

*Each done when: it works on a hosted demo course with a paying-tier license.*

---

## Suggested next session (top 5, in order)

1. A1 SCORM Cloud conformance run (highest risk to the whole value proposition)
2. A3 pypdf extraction switch (cheap, big quality lift for PDF-driven courses)
3. B1 Adapt go/no-go spike (unblocks the editor decision)
4. C2 ten-minute tutorial + gallery (needed for any pilot/customer conversation)
5. D1 Stripe → license automation (unblocks actually charging anyone)
