# Worklog

Append concise entries here when project state changes. Keep entries factual: what changed, why, tests run, and remaining risk.

## 2026-06-17

### Baseline Orientation

- Current repo remote: `https://github.com/ratsam93/course_pack_elearning.git`.
- `git pull --ff-only` reported the project was already up to date.
- Early local research inputs were used during the design phase and then folded into the current implementation.
- Baseline tests passed on the local product code.
- Focused lint passed on `src` and `tests`.

### Rotation System Added

- Added `docs/project-rotation.md` as the repeatable trigger checklist.
- Added `docs/contributor-onboarding.md` for new engineers.
- Added `docs/task-board.md` as the source of truth for task ownership and status.
- Updated `README.md` to point new contributors to the rotation system.

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
