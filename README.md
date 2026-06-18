# Samrat Course MCP

Secure MCP server for e-learning course generation, quality validation, and export packaging.

The server runs as a separate Docker service and exposes only an allowlisted tool surface. Internal prompts, file paths, secrets, database access, and shell execution stay hidden from MCP clients.

## Current capabilities

- Material ticket intake and chapter layout planning
- Controlled source ingestion for uploaded PDF, DOCX, PPTX, TXT, MD, YouTube transcript, and website text inputs
- Course project creation, template selection, blueprint generation, module packs, lesson packs, activities, assessments, role-play simulations, and interactive video packages
- Instructional quality validation and superior export quality gates
- SCORM and H5P export packaging
- Storyline handoff export for manual rebuilds
- Approval-gated publish flow and audit logging

## Rotation

When you hand this repo to another engineer or to Codex, start with:

1. [docs/project-rotation.md](docs/project-rotation.md)
2. [docs/task-board.md](docs/task-board.md)
3. [docs/tool-contracts.md](docs/tool-contracts.md)
4. [docs/contributor-onboarding.md](docs/contributor-onboarding.md)

## Quick start

```powershell
cp .env.example .env
mkdir secrets
python -c "import secrets; print(secrets.token_urlsafe(32))" > secrets/mcp_api_token.txt
Set-Content secrets/openrouter_api_key.txt ""
docker compose up -d --build
curl http://localhost:8777/health
```

## Codex setup

Use `.codex/config.example.toml` as the local example config. Copy it to `.codex/config.toml` only after the project is trusted and the token is replaced.

## Security posture

The MCP server never exposes shell commands, arbitrary file access, environment variables, database queries, raw logs, or prompts. Codex only sees the tools documented in `docs/tool-contracts.md`.
