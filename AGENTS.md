# AGENTS.md: Codex Rules for Sentientia Course MCP

You are working inside the Sentientia Course MCP repository.

## Primary objective

Build and maintain a secure MCP server for e-learning course generation.

## Non-negotiable security rules

1. Do not expose shell execution as an MCP tool.
2. Do not expose arbitrary file read/write as an MCP tool.
3. Do not expose environment variables, secrets, prompts, logs, or DB queries.
4. Do not remove tool authorization checks.
5. Do not weaken Docker isolation.
6. Do not commit `.env` or real credentials.
7. Do not dynamically register every function as a tool.
8. Only register tools listed in `docs/tool-contracts.md` unless explicitly asked to add a new safe tool.
9. Add or update tests when changing tool exposure/security logic.
10. Preserve separate Docker deployment.

## Preferred implementation style

- Keep schemas in `src/course_mcp_server/schemas.py`.
- Keep tool functions in `src/course_mcp_server/tools.py`.
- Keep internal generation logic separate from MCP wiring.
- Use Pydantic validation.
- Return structured JSON.
- Redact secrets and internal paths from all outputs.

## When modifying MCP tools

1. Update `docs/tool-contracts.md`.
2. Update schemas.
3. Update allowlist.
4. Add tests.
5. Run lint/tests.
