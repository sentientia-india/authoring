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

