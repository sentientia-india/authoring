# PRD: Samrat Course MCP

## 1. Product name

**Samrat Course MCP**

## 2. One-line description

A licensed MCP server that turns the user's own Claude Code / Codex subscription into a production-grade course factory: the calling agent authors all content, the MCP validates, gamifies, and packages it into a Level 3.5/4 SCORM zip.

## 3. Background

Existing AI course creators can generate outlines, lessons, quizzes, and publishable mini courses. Mini Course Generator's public MCP positioning focuses on connecting AI clients to course planning, generation, and publishing; Coursebox.ai adds AI images, branching scenarios, avatar videos, an AI tutor, and white-label selling. The opportunity is to build a more production-grade, domain-specific version for professional training businesses, especially e-learning, compliance, SOP, airline, safety, sales enablement, onboarding, and certification programs.

## 3b. Business model (fixed constraint)

The MCP server is the product and the licensing gate: without a valid license key, no course can be created. All expensive work — lesson prose, quiz writing, image generation — runs on the **user's own Claude Code or Codex subscription**. The MCP performs only cheap deterministic work (validation, quality gates, media briefs, PDF extraction, SCORM packaging), so operating cost stays near zero while content quality rides on the frontier model the user already pays for. The server retains a small internal LLM hook (OpenRouter) strictly for minor helper tasks, never full authoring.

## 4. Problem

Training teams spend too much time turning raw materials into structured courses. AI can help, but normal chat-based generation is not production-safe because it lacks:

- repeatable schemas
- source grounding
- review workflow
- LMS export support
- auditability
- controlled tool exposure
- secure container isolation
- team-ready deployment

## 5. Objectives

### Business objectives

1. Reduce first-draft course creation time by at least 70%.
2. Convert internal PDFs/SOPs/PPTs/video transcripts into LMS-ready course drafts.
3. Support instructional designer review before publishing.
4. Enable Codex-assisted development without exposing internal source, prompts, or credentials.
5. Build a modular MCP layer that can later connect to Moodle, Canvas, custom LMS, SCORM, H5P, and WhatsApp nudges.

### Product objectives

1. Generate course outline from topic/source material.
2. Generate lesson content with learning objectives and estimated duration.
3. Generate quizzes, scenarios, flashcards, and role-play activities.
4. Generate SCORM/H5P-ready export structures.
5. Provide secure publish/update hooks for LMS integration.
6. Maintain audit logs for every agent-triggered action.

## 6. Success metrics

| Metric | Target |
|---|---:|
| Time to generate first complete course draft | < 10 minutes |
| User questions asked before a plan is proposed | <= 3 |
| Exported courses containing placeholder/duplicated content | 0% (quality gate blocks) |
| Server-side LLM/image generation cost per course | ~0 (user's agent pays) |
| Instructional designer acceptance of first outline | >= 75% |
| Quiz schema validation success | >= 95% |
| SCORM package validation success | >= 90% in MVP, >= 98% post-MVP |
| Course creation without a valid license | 0 |
| Unauthorized tool access attempts blocked | 100% |
| Secrets exposed to Codex | 0 |
| Tools visible to Codex beyond allowlist | 0 |
| Container runs as non-root | 100% deployments |
| Critical/high dependency vulnerabilities | 0 before production release |

## 7. Users

### Primary users

- Instructional designers
- L&D managers
- Training operations teams
- E-learning vendors
- Course creators
- Compliance trainers

### Technical users

- Developer using Codex
- Backend engineer
- DevOps engineer
- Security reviewer

## 8. Core use cases

### Use case 1: Topic to course

User gives a topic such as "Airline emergency evacuation training for cabin crew". The MCP generates a structured outline, lessons, quiz, scenarios, and completion assessment.

### Use case 2: Document to course

User uploads/points to a processed text source extracted from PDF, PPT, SOP, policy, or transcript. The MCP generates a source-grounded course.

### Use case 3: Course improvement

User asks Codex or another MCP client to refine the course for a specific audience, tone, duration, or Bloom's taxonomy level.

### Use case 4: Quiz and assessment

MCP creates MCQs, scenario questions, scoring rules, passing criteria, remediation feedback, and retake rules.

### Use case 5: Export

MCP generates an export-ready package structure for SCORM 1.2/2004, H5P, or internal LMS ingestion.

### Use case 6: LMS publish

MCP submits a reviewed course package to a connected LMS using a scoped integration token. Publishing is a high-risk action and must support human approval.

## 9. MVP scope

### Included (shipped as of 2026-07-11)

- MCP server with allowlisted tools only
- Dockerized separate service
- Per-customer license keys with tiers (free/pro/white_label), monthly export quotas, and metering; admin bootstrap token retained
- Tool-level permission checks and JSON schema validation
- Course project lifecycle
- Three-question discovery interview (`course_brief_line`, `duration_preset`, `media_plan_mode`) with AI-derived brief fields and a one-shot plan approval (`propose_course_plan` / `approve_course_plan`)
- Controlled source ingestion by upload ID (PDF/DOCX/PPTX/TXT/MD/YouTube/website; deterministic extraction, no LLM cost)
- Agent-authored content pipeline: `submit_course_content` (one-shot) and `submit_course_module` (parallel, idempotent per module)
- Media pipeline with zero server generation cost: deterministic image briefs + video slots (`get_media_briefs`), agent upload channel (`upload_media_asset`), block-level attachment (`attach_media`), packaged into the zip
- Level 3.5/4 SCORM player: dark game HUD, full-screen slide lessons, locked progression, streaks, timed challenges, branching character scenes, confetti celebration, printable certificate — all selectable per course via `game_options`
- Instructional quality validator + superior quality gate (blocks export on placeholder/duplicated content, including leaked writer meta-instructions)
- SCORM 1.2/2004 and H5P export packaging; white-label branding on the white_label tier
- Separate drag-and-drop SCORM editor service (`apps/scorm_editor`); Adapt Authoring adoption evaluated as future replacement
- Audit logging, rate limiting, health endpoint
- Codex project config example and CI workflow for lint/test/security checks

### Excluded from MVP (deferred to hosted phase)

- Live hosted landing pages / share links
- Full LMS learner portal
- Payment/gated course sales
- AI tutor chatbot and AI grading of open answers
- Live video generation and voiceover rendering
- Full production SCORM conformance engine (SCORM Cloud certification pending)
- Direct unreviewed publishing to customer LMS

## 10. Post-MVP scope

- Moodle/Canvas/custom LMS publish adapters
- H5P content generator
- YouTube transcript ingestion
- PPT/PDF extraction pipeline
- Image/diagram generation
- Certificate generation
- Learner enrollment and completion webhooks
- WhatsApp/Telegram learning nudges
- Analytics dashboard
- White-label tenant settings
- Human-in-the-loop review UI

## 11. Functional requirements

### FR-001: Create course project

The MCP shall create a tenant-scoped course project with review lifecycle status.

### FR-002: Ingest controlled source

The MCP shall ingest source material by controlled upload ID, not arbitrary file path.

### FR-003: Generate blueprint

The MCP shall generate a structured course outline with modules, lessons, learning objectives, prerequisites, assessment points, and estimated duration.

### FR-004: Generate lesson

The MCP shall generate lesson content for a specific module and audience.

### FR-005: Generate assessment

The MCP shall generate quizzes with answer keys, explanations, difficulty, and mapped learning objectives.

### FR-006: Generate scenario

The MCP shall generate practical role-play or case-study scenarios.

### FR-007: Validate instructional quality

The MCP shall score generated courses for objective quality, alignment, source grounding, accessibility, compliance, repetition, and completeness.

### FR-008: Export package

The MCP shall create a validated SCORM package from generated project artifacts.

### FR-009: Tool allowlist

The MCP shall expose only approved course-related tools to Codex.

### FR-010: Audit logging

The MCP shall log request ID, tenant ID, user ID, tool name, action type, input hash, output hash, and policy decision.

### FR-008: Approval gates

The MCP shall require approval for publishing, overwriting courses, deleting content, or sending learner-facing messages.

## 12. Non-functional requirements

| Area | Requirement |
|---|---|
| Security | OAuth/API key now, OAuth 2.1-ready later, tool-level RBAC, least privilege |
| Privacy | No raw secrets or private source code returned to agent |
| Performance | Outline generation < 30s for normal source sizes |
| Reliability | Healthcheck, restart policy, CI test gate |
| Observability | Structured logs, request IDs, audit trails |
| Deployment | Separate Docker container, isolated network, non-root user |
| Maintainability | Tool contracts versioned and schema-driven |
| Compliance | Support future SOC2/GDPR-style controls |

## 13. MCP tool surface

The authoritative, tested tool list lives in `docs/tool-contracts.md` (allowlist enforced in `security.py`, registry in `tools.py`, exact-set tested). The primary content path:

1. Interview: `start_course_discovery` → `save_course_discovery_answer` (3 essentials) → `ingest_course_source` (optional PDF/doc)
2. Plan: `propose_course_plan` → `approve_course_plan` (one-shot approval)
3. Author (user's agent, parallel): `submit_course_module` × N, or `submit_course_content` one-shot
4. Media: `get_media_briefs` → agent generates → `upload_media_asset` → `attach_media`
5. Gate & ship: `validate_instructional_quality` / `validate_superior_course_quality` → `build_export_package` (license-metered)

Supporting tools: template listing/recommendation, granular outline/lesson/assessment/interaction approvals (power users), interactive video, Storyline handoff, status, artifacts, publish approval.

Tools intentionally not exposed:

- `read_file`
- `write_file`
- `shell_exec`
- `get_env`
- `query_database`
- `dump_prompts`
- `list_internal_jobs`
- `admin_publish_without_review`

## 14. Security requirements

1. The MCP server must run in its own Docker container.
2. Container must run as a non-root user.
3. Filesystem should be read-only except `/tmp` and declared output volume.
4. No Docker socket mount.
5. No host project source mount in production.
6. No unrestricted network egress.
7. Only allowlisted MCP tools can be registered.
8. Every tool must validate input with Pydantic schemas.
9. Every tool must pass through authorization middleware.
10. Responses must be redacted for secrets and internal paths.
11. Internal prompts must stay server-side and never be returned.
12. High-risk tools must require explicit approval.
13. Logs must not contain raw secrets or full source documents.

## 15. Release criteria

- All tests pass.
- Docker image builds.
- Healthcheck passes.
- Tool allowlist test passes.
- Security tests pass.
- CI passes.
- Dependency vulnerability check passes or approved exception exists.
- `docs/deployment.md` tested on staging server.

## 16. Open decisions

| Decision | Default recommendation |
|---|---|
| Stack | Python FastMCP + Pydantic + Docker |
| Initial transport | HTTP MCP endpoint for Codex; stdio can be added for local dev |
| Storage | PostgreSQL later; local JSON artifact store for MVP |
| Queue | Redis/Celery later for long-running exports |
| LMS target | Start with SCORM scaffold, then Moodle/Canvas adapters |
| Auth | Bearer token in MVP, OAuth 2.1 path for production |
