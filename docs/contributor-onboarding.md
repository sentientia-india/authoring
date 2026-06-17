# Contributor Onboarding

This project is a secure MCP server for e-learning course generation. The main job is to make course generation useful while keeping Codex and other MCP clients away from internals, secrets, files, shell, logs, database queries, and Docker control.

## Read First

Read these files in order:

1. `AGENTS.md`
2. `README.md`
3. `docs/project-rotation.md`
4. `docs/task-board.md`
5. `docs/tool-contracts.md`
6. `SECURITY.md`
7. `DEVBOOK.md`

## Local Baseline

Run these before coding:

```powershell
git status --short
python -m pytest
python -m ruff check src tests
```

Do not run or modify `.codex/reference-repos` as part of normal product work.

## Important Files

- `src/course_mcp_server/server.py`: MCP server setup and tool registration wrapper.
- `src/course_mcp_server/security.py`: tool allowlist, auth, redaction, audit helpers.
- `src/course_mcp_server/schemas.py`: Pydantic request and response schemas.
- `src/course_mcp_server/tools.py`: only exposed MCP tool handlers.
- `src/course_mcp_server/course_generator.py`: internal generation orchestration.
- `src/course_mcp_server/exporters/scorm.py`: SCORM artifact builder.
- `docs/tool-contracts.md`: public MCP tool contract.
- `tests/`: security and tool exposure tests.

## Coding Rules

- Keep MCP-exposed functions in `tools.py`.
- Keep schemas in `schemas.py`.
- Keep private generation logic out of MCP wiring.
- Return structured JSON.
- Redact secrets and internal paths from outputs.
- Add tests for security-sensitive changes.
- Do not dynamically register every function as an MCP tool.
- Do not add shell, file manager, env, database, Docker, prompt, or log tools.

## Handoff Note Format

Every contributor should provide this after a task:

```markdown
## Handoff

Task:
Files changed:
Security impact:
Tests added:
Commands run:
Known gaps:
```

