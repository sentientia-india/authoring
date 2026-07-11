# Samrat Course MCP

Licensed MCP server that turns the user's own Claude Code / Codex subscription into a course factory: the calling agent authors all content, the MCP validates, gamifies, and packages it into a Level 3.5/4 SCORM zip.

The server runs as a separate Docker service and exposes only an allowlisted tool surface. Internal prompts, file paths, secrets, database access, and shell execution stay hidden from MCP clients. All expensive work (writing, image generation) runs on the caller's subscription — the MCP does only cheap deterministic work.

## Current capabilities

- Three-question discovery interview with AI-derived brief and one-shot plan approval
- Controlled source ingestion for uploaded PDF, DOCX, PPTX, TXT, MD, YouTube transcript, and website text inputs (deterministic extraction, no LLM cost)
- Agent-authored content pipeline: one-shot `submit_course_content` or parallel `submit_course_module`
- Zero-cost media pipeline: deterministic image briefs + video slots, agent upload channel, block-level media attachment, packaged into the zip
- Level 3.5/4 SCORM player: dark game HUD, full-screen slide lessons, locked progression, streaks, timed challenges, branching character scenes, confetti, printable certificate — selectable per course
- Instructional quality validation and superior export quality gates (placeholder/duplicate content blocks export)
- SCORM 1.2/2004 and H5P export packaging; white-label branding on the white_label tier
- Per-customer license keys with tiers and monthly export quotas (`scripts/issue_license.py`)
- Approval-gated publish flow and audit logging

Start with the agent playbook in [docs/tool-contracts.md](docs/tool-contracts.md).

## Product surfaces

This repo is split into two runtime surfaces:

1. `course-mcp`: the secure MCP generation, validation, and export service.
2. `scorm-editor`: a separate drag-and-drop editor service for polishing uploaded SCORM exports.

Keep them deployed from the same GitHub repo but running as separate Docker services with separate Dockerfiles. See [docs/service-split.md](docs/service-split.md).

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
curl http://localhost:8788/
```

## Codex setup

Use `.codex/config.example.toml` as the local example config. Copy it to `.codex/config.toml` only after the project is trusted and the token is replaced.

## Security posture

The MCP server never exposes shell commands, arbitrary file access, environment variables, database queries, raw logs, or prompts. Codex only sees the tools documented in `docs/tool-contracts.md`.
