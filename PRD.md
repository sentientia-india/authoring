# PRD: Sentientia Course MCP

## 1. Product name

**Sentientia Course MCP**

## 2. One-line description

A secure MCP server that lets Codex and AI clients create structured, interactive, LMS-ready e-learning courses without exposing the private internals of the course-generation system.

## 3. Background

Existing AI course creators can generate outlines, lessons, quizzes, and publishable mini courses. Mini Course Generator's public MCP positioning focuses on connecting AI clients to course planning, generation, and publishing. The opportunity is to build a more production-grade, domain-specific version for professional training businesses, especially e-learning, compliance, SOP, airline, safety, sales enablement, onboarding, and certification programs.

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
| Instructional designer acceptance of first outline | >= 75% |
| Quiz schema validation success | >= 95% |
| SCORM package validation success | >= 90% in MVP, >= 98% post-MVP |
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

### Included

- MCP server with allowlisted tools only
- Dockerized separate service
- API-token authentication
- Tool-level permission checks
- JSON schema validation
- Course outline generator
- Lesson generator
- Quiz generator
- Scenario/role-play generator
- SCORM package scaffold generator
- Audit logging
- Health endpoint
- Codex project config example
- CI workflow for lint/test/security checks

### Excluded from MVP

- Full WYSIWYG authoring UI
- Full LMS learner portal
- Payment/gated course sales
- Live video generation
- Voiceover rendering
- Full production SCORM conformance engine
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

### FR-001: Generate outline

The MCP shall generate a structured course outline with modules, lessons, learning objectives, prerequisites, assessment points, and estimated duration.

### FR-002: Generate lesson

The MCP shall generate lesson content for a specific module and audience.

### FR-003: Generate quiz

The MCP shall generate quizzes with answer keys, explanations, difficulty, and mapped learning objectives.

### FR-004: Generate scenario

The MCP shall generate practical role-play or case-study scenarios.

### FR-005: Export package scaffold

The MCP shall create a validated course package folder structure that can later be converted into SCORM/H5P/LMS content.

### FR-006: Tool allowlist

The MCP shall expose only approved course-related tools to Codex.

### FR-007: Audit logging

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

MVP tools exposed to Codex:

1. `generate_course_outline`
2. `generate_lesson_draft`
3. `generate_quiz_bank`
4. `generate_roleplay_scenario`
5. `validate_course_schema`
6. `build_scorm_package_scaffold`
7. `get_course_generation_status`

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
