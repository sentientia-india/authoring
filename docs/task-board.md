# Task Board

This is the project-level source of truth for work status. Update it whenever work is assigned, started, blocked, integrated, or completed.

## Status Key

- `Ready`: clear enough for a contributor to start.
- `In Progress`: someone is actively coding it.
- `Review`: code exists and needs review/integration.
- `Blocked`: cannot move without a decision or dependency.
- `Done`: integrated, tested, and documented.

## Active Work

| ID | Status | Owner | Task | Files | Acceptance |
|---|---|---|---|---|---|
| T-001 | Done | Codex | Add structured response schemas for all MVP tools. | `src/course_mcp_server/schemas.py`, `tests/` | Pydantic response models exist and tests validate successful tool output shape. |
| T-002 | Done | Codex | Replace legacy course generation with a private generation service interface. | `src/course_mcp_server/course_generator.py`, `src/course_mcp_server/schemas.py`, `tests/` | Generators return validated structured data and never expose prompts/provider internals. |
| T-003 | Done | Codex | Build real SCORM package output with zip creation and path safety. | `src/course_mcp_server/exporters/scorm.py`, `tests/` | Creates a package under configured output dir, rejects unsafe slugs/paths, includes manifest and HTML pages. |
| T-004 | Done | Codex | Add minimal internal job store and status tracking. | `src/course_mcp_server/`, `tests/` | Known job IDs return scoped status; unrelated or unknown IDs reveal nothing. |
| T-005 | Done | Codex | Add source text normalization and instructional-design checks. | `src/course_mcp_server/course_generator.py`, `src/course_mcp_server/schemas.py`, `tests/` | Source text is treated as untrusted content and outputs include objective/module validation notes. |
| T-007 | Done | Codex | Apply Sprint 1 repeatable polished SCORM generator. | `src/course_mcp_server/exporters/scorm.py`, `tests/test_scorm_export.py` | Generated SCORM packages include responsive template, assets, interactive JS, SVG visuals, video embed support, score/completion helpers, and validation tests. |
| T-008 | Done | Codex | Apply Sprint 2 source ingestion and artifact service hardening. | `src/course_mcp_server/ingestion.py`, `src/course_mcp_server/tools.py`, `tests/` | Controlled uploads extract raw text, DOCX, PPTX/PPT, YouTube transcript text, and basic PDF text with references. |
| T-009 | Done | Codex | Apply Sprint 3 H5P-style activities and LMS adapter internals. | `src/course_mcp_server/activities.py`, `src/course_mcp_server/lms_adapters.py`, `tests/` | Activities return H5P-style schemas and LMS publish plans remain approval-gated/internal. |
| T-010 | Done | Codex | Apply Sprint 4 quality, analytics, and certificate internals. | `src/course_mcp_server/quality.py`, `src/course_mcp_server/analytics.py`, `tests/` | Quality validation checks alignment/source/completeness and analytics/certificate helpers return structured metadata. |
| T-011 | Done | Codex | Add controlled H5P export and stricter SCORM runtime validation. | `src/course_mcp_server/exporters/`, `src/course_mcp_server/tools.py`, `tests/` | `build_export_package` supports SCORM and H5P, SCORM runtime records interactions/status, and package validators cover required files. |
| T-012 | Done | Codex | Add production internals for storage, queue, audit, rate limit, and certificates. | `src/course_mcp_server/`, `docker-compose.yml`, `tests/` | Internal Postgres/Redis config exists, JSON fallback is tested, audit persistence/rate limiting run inside server path, artifacts get metadata URIs, certificates render to HTML. |
| T-013 | Done | Codex | Add download-only export delivery metadata for BYO LMS SaaS model. | `src/course_mcp_server/delivery.py`, `src/course_mcp_server/tools.py`, `tests/` | SCORM/H5P exports include delivery metadata indicating no hosted storage is required and customers should download/upload to their own LMS. |
| T-014 | Done | Claude | Agent-authored content pipeline: submit_course_content + course_schema_v2 validation, remove server-side filler fabrication, quality gate catches leaked writer meta-instructions. | `src/course_mcp_server/tools.py`, `schemas.py`, `instructional_quality.py`, `tests/` | Authored prose flows through to SCORM export; filler course impossible when content submitted; test fixture drives full flow. |
| T-015 | Done | Claude | Level 3.5/4 SCORM player: dark game HUD, slide lessons, locked progression, streaks, timed challenges, branching character scenes, confetti, certificate; per-course game_options; media blocks (image/video/link) packaged into zip. | `src/course_mcp_server/exporters/scorm.py`, `exporters/static/game_theme.css`, `exporters/static/game_player.js`, `course_schema_v2.py` | Verified in browser end-to-end: gating, timer, XP/streak, unlock, confetti, media rendering. |
| T-016 | Done | Claude | Three-question interview + one-shot plan approval; media briefs + upload channel + attach_media; parallel submit_course_module; licensing tiers with export quotas and white-label branding. | `discovery/`, `media_briefs.py`, `licensing.py`, `scripts/issue_license.py`, `tools.py`, `tests/test_licensing.py` | E2E script: 3 answers → plan → parallel modules → briefs → upload → attach → metered export; 120 tests green. |

## Backlog

| ID | Status | Task | Notes |
|---|---|---|---|
| B-001 | Done | H5P packaging research spike | Safe integration plan captured in `docs/export-adapters.md`; no arbitrary file tools. |
| B-002 | Done | LiaScript export research spike | Safe internal adapter plan captured in `docs/export-adapters.md`; no arbitrary git/file export through MCP. |
| B-003 | Ready | LMS adapter planning | Future only; publishing requires human approval and must not be in MVP tool surface. |
| B-004 | Done | Human approval workflow | Internal approval policy added; no publish/deploy/upload tools exposed. |
| B-005 | Done | Real LLM provider adapter | OpenRouter adapter added behind internal generation service; prompts, provider logs, and raw errors are not exposed. |
| B-006 | Done | SCORM validator integration | Internal zip/manifest/SCO validation added for generated packages. |
| B-007 | Done | Repeatable polished SCORM generator | Sprint 1 applied: polished template output is now generated by the exporter, not hand-built artifacts. |
| B-008 | Done | Source ingestion engine | Safe controlled upload extractors added without raw file browsing tools. |
| B-009 | Done | H5P-style activity library | Activity schema covers flashcards, matching, branching, timeline, fill blanks, reflection, and related patterns. |
| B-010 | Done | Internal LMS publishing plans | Moodle, Canvas, and custom LMS adapter plans require secret files and human approval. |
| B-011 | Done | Analytics and certificates | Internal metrics summary and recertification certificate metadata helpers added. |
| B-012 | Done | H5P package export | Safe `.h5p` zip generation added from internal activity JSON only. |
| B-013 | Done | Production storage and queue foundation | Compose provisions Postgres/Redis, app includes storage/queue abstractions with safe fallback. |
| B-014 | Done | Audit, rate limit, and certificate rendering | Audit persistence, per-user rate limit, artifact metadata, and certificate HTML renderer added. |

## Integration Queue

No external code is currently waiting for integration.
