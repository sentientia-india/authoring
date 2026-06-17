# Samrat Course MCP

Production-ready MCP project skeleton for generating e-learning courses, quizzes, role-play scenarios, H5P/SCORM-ready course packages, and LMS publishing workflows.

This project is designed to run as a **separate Docker instance** from any existing application container. The MCP server exposes only a small allowlisted surface to Codex/AI agents and keeps internal prompts, pipelines, source files, databases, and environment secrets hidden.

## Project rotation

When this project is handed to Codex, a new engineer, or an external contractor, start with [docs/project-rotation.md](docs/project-rotation.md). That checklist is the trigger system for reading current state, choosing work from [docs/task-board.md](docs/task-board.md), reviewing prior changes in [docs/worklog.md](docs/worklog.md), and integrating outside code safely.

New contributors should read [docs/contributor-onboarding.md](docs/contributor-onboarding.md) before coding.

## What this MCP should beat

Mini Course Generator publicly exposes an MCP experience around planning, generating, and publishing courses from MCP-compatible AI clients. This project goes beyond that by adding:

- Domain-specific course generation for airline, compliance, SOP, safety, sales, and onboarding training.
- Course generation from PDF/PPT/DOCX/video transcript/source text.
- Instructional design checks before publishing.
- Quiz, flashcard, role-play, scenario, assessment, certificate, and recertification flows.
- SCORM/H5P/LMS export strategy.
- Security-first MCP exposure model for Codex.
- Docker-isolated deployment and CI checks.

## Repository layout

```text
.
├── AGENTS.md                         # Codex working rules
├── PRD.md                            # Dedicated product requirements document
├── DEVBOOK.md                        # Developer book for implementation and deployment
├── SECURITY.md                       # Security model and MCP exposure policy
├── docker-compose.yml                # Separate Docker service
├── Dockerfile                        # Hardened container image
├── pyproject.toml                    # Python project definition
├── .env.example                      # Safe env template
├── .codex/config.example.toml        # Codex MCP config example
├── docs/
│   ├── prd-form.md                   # Fillable PRD form
│   ├── github-repo-research.md       # GitHub repo research and usage plan
│   ├── architecture.md               # Production architecture
│   ├── tool-contracts.md             # MCP tools and schemas
│   ├── deployment.md                 # Docker deployment, rollback, operations
│   └── codex-attachment.md           # How to attach this MCP to Codex
├── src/course_mcp_server/
│   ├── server.py                     # MCP server entrypoint
│   ├── security.py                   # auth, allowlist, redaction helpers
│   ├── schemas.py                    # Pydantic request/response models
│   ├── tools.py                      # exposed MCP tools only
│   ├── course_generator.py           # internal generation orchestration placeholder
│   └── exporters/scorm.py            # SCORM package placeholder
├── tests/
│   ├── test_tool_allowlist.py
│   └── test_security.py
└── scripts/
    ├── bootstrap.sh
    └── push_to_github.sh
```

## Quick start

```bash
cp .env.example .env
# edit .env with your secrets; do not commit it

docker compose up -d --build
curl http://localhost:8777/health
```

## LLM provider

Generation can use OpenRouter internally. Set `OPENROUTER_API_KEY` in `.env`; the default model is `nvidia/nemotron-3-ultra-550b-a55b:free`. If no key is configured, the server uses deterministic local generation so tests and development still work.

## Attach to Codex

Use `.codex/config.example.toml` as your project-scoped MCP example. Copy it into `.codex/config.toml` only after replacing the token and endpoint.

## Security posture

The MCP server never exposes:

- raw project files
- shell/exec commands
- environment variables
- database query tools
- internal prompt templates
- private pipeline logs
- unrestricted file read/write
- external network fetch without allowlist

Codex only sees the tools defined in `src/course_mcp_server/tools.py` and described in `docs/tool-contracts.md`.
