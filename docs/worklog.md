# Worklog

Append concise entries here when project state changes. Keep entries factual: what changed, why, tests run, and remaining risk.

## 2026-06-17

### Baseline Orientation

- Current repo remote: `https://github.com/ratsam93/course_pack_elearning.git`.
- `git pull --ff-only` reported the project was already up to date.
- Reference repos were cloned locally under `.codex/reference-repos/` for research only.
- Baseline tests: `python -m pytest` passed with 7 tests.
- Focused lint: `python -m ruff check src tests` passed.
- Full `python -m ruff check .` is not meaningful while local reference repos are present unless they are ignored or excluded.

### Rotation System Added

- Added `docs/project-rotation.md` as the repeatable trigger checklist.
- Added `docs/contributor-onboarding.md` for new engineers.
- Added `docs/task-board.md` as the source of truth for task ownership and status.
- Added `docs/reference-repos.md` to record cloned research repos and intended use.
- Updated `README.md` to point new contributors to the rotation system.
- Ignored `.codex/reference-repos/` so cloned external repos do not become product source.

### MVP Implementation Pass

- Added Pydantic response schemas for outline, lesson, quiz, role-play, validation, SCORM package, and job status outputs.
- Updated internal generators to return schema-validated structured data.
- Added source-text risk flags for instruction-injection and secret-like source content.
- Replaced the SCORM placeholder with manifest, index page, module pages, a small runtime shim, and zip package creation.
- Added path containment checks for SCORM artifact output.
- Added a minimal internal JSON job store and tenant-scoped status lookup.
- Added tests for generation output schemas, SCORM packaging, and job status scoping.
- Verification: `python -m pytest` passed with 12 tests.
- Verification: `python -m ruff check .` passed.

### OpenRouter Adapter

- Added internal OpenRouter chat-completions adapter using the OpenAI-compatible endpoint.
- Default model is `nvidia/nemotron-3-ultra-550b-a55b:free`.
- Added `.env.example` settings for `OPENROUTER_API_KEY`, model, base URL, timeout, and app title.
- Wired outline, lesson, quiz, and role-play generation through OpenRouter when `OPENROUTER_API_KEY` is configured.
- Kept deterministic fallback when the key is missing or provider output is invalid.
- Provider errors are converted to safe internal messages and raw response bodies are not exposed to MCP clients.

### Completion Pass

- Added OpenRouter retry/backoff settings and tests for transient network and 5xx failures.
- Added optional live OpenRouter smoke test that runs only when `OPENROUTER_API_KEY` is present.
- Added internal SCORM package validation for zip readability, required files, manifest root, and SCO declaration.
- Added internal human approval policy for high-risk publish/upload actions without exposing new MCP tools.
- Added `docs/export-adapters.md` with safe H5P and LiaScript adapter plans.

### Sprint 1 Applied

- Upgraded SCORM exporter from minimal scaffold to repeatable polished template.
- Generated packages now include responsive CSS, interactive course JavaScript, SCORM score/completion helpers, SVG visuals, module pages, and approved YouTube embed support.
- Added tests proving generated packages include assets and responsive/interactivity markers.
- Verification: `python -m pytest` passed with 25 tests and 1 skipped optional live OpenRouter test.
- Verification: `python -m ruff check .` passed.
- Verification: `bandit -r src -q` passed.

### Sprint 2-4 Applied

- Added controlled source ingestion extractors for raw text, DOCX, PPT/PPTX, YouTube transcript text, website text files, and basic text-based PDF extraction.
- Added H5P-style activity generation schemas informed by the local `scorm-h5p-wrapper` reference pattern for xAPI completion/score events.
- Added internal LMS publish plans for Moodle, Canvas, and custom LMS with human approval required and no public publish tool.
- Added instructional quality validation service for measurable objectives, source grounding, lesson/assessment alignment, and content completeness.
- Added internal analytics and certificate metadata helpers for completion count, attempt count, time spent, score, and recertification due dates.
- Wired the existing MCP lifecycle tools to the new ingestion, activity, and quality services without expanding the allowlist.

### Export Completion Pass

- Added controlled H5P `.h5p` package export from internal activity JSON through `build_export_package`.
- Strengthened SCORM runtime helper to record score bounds, SCORM 2004 success status, and learner interactions.
- Strengthened SCORM validation to flag missing runtime tracking behavior.
