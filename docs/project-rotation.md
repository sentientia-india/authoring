# Project Rotation System

Use this document every time the project is rotated to Codex, a new engineer, or an external contractor. It is the trigger checklist for understanding current state, picking up work, and handing work back safely.

## Rotation Trigger

Start here whenever someone says:

- "rotate this project"
- "continue this project"
- "new developer is joining"
- "what should the coder do next"
- "integrate someone else's code"

## Required First Pass

1. Read `AGENTS.md`.
2. Read `README.md`.
3. Read `docs/task-board.md`.
4. Read `docs/worklog.md`.
5. Read `docs/tool-contracts.md`.
6. Run:

```powershell
git status --short
python -m pytest
python -m ruff check src tests
```

## Security Gate

Before accepting or integrating any code, confirm:

- No shell execution is exposed as an MCP tool.
- No arbitrary file read/write is exposed as an MCP tool.
- No environment, prompt, log, or database dump tool exists.
- `TOOL_REGISTRY` still matches `ALLOWED_TOOLS`.
- Any changed exposed tool is documented in `docs/tool-contracts.md`.
- Tests were added or updated for tool exposure, redaction, path safety, and validation.

## Contributor Handoff Flow

1. Assign work from `docs/task-board.md`.
2. Tell the contributor to read `docs/contributor-onboarding.md`.
3. Ask for a short implementation note with:
   - files changed
   - security impact
   - tests added
   - commands run
4. Integrate only after reviewing tests and security rules.
5. Record the integration result in `docs/worklog.md`.
6. Update `docs/task-board.md` status and next action.

## Done Definition

A task is done only when:

- product code compiles/imports
- relevant unit tests pass
- `python -m ruff check src tests` passes
- docs are updated when contracts or workflow change
- no AGENTS.md security rule is violated
