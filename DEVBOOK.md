# Developer Book: Samrat Course MCP

## 1. Purpose

This Dev Book gives engineers and Codex a clear implementation guide for a production-grade MCP server that creates e-learning courses while keeping internal systems protected.

## 2. Design principles

1. Expose capabilities, not internals.
2. Use schema-driven tools.
3. Keep generation pipelines private.
4. Enforce least privilege by default.
5. Require approval for high-risk actions.
6. Run the MCP server in an isolated Docker service.
7. Keep Codex productive but constrained.

## 3. Architecture overview

```text
Codex / MCP Client
        │
        ▼
MCP Transport Layer
        │
        ▼
Auth + Tool Policy Gateway
        │
        ▼
Allowlisted MCP Tools
        │
        ▼
Internal Course Generation Services
        │
        ├── Outline Engine
        ├── Lesson Engine
        ├── Quiz Engine
        ├── Role-play Engine
        ├── Export Engine
        └── LMS Adapter Layer
        │
        ▼
Artifact Store / LMS / SCORM Output
```

## 4. Components

### 4.1 MCP server

Location: `src/course_mcp_server/server.py`

Responsibilities:

- Initialize MCP server.
- Register only allowlisted tools.
- Provide health endpoint if HTTP transport is used.
- Apply redaction and audit hooks.

### 4.2 Security policy

Location: `src/course_mcp_server/security.py`

Responsibilities:

- Validate API token.
- Enforce tool allowlist.
- Redact secrets from outputs.
- Deny internal/admin/system functions.
- Generate audit events.

### 4.3 Schemas

Location: `src/course_mcp_server/schemas.py`

Responsibilities:

- Define request and response models.
- Keep tool inputs strict.
- Prevent arbitrary object injection.

### 4.4 Course generator

Location: `src/course_mcp_server/course_generator.py`

Responsibilities:

- Convert normalized inputs into structured learning objects.
- Map content to objectives, lessons, quizzes, and scenarios.
- Keep internal prompt strategy private.

### 4.5 Exporters

Location: `src/course_mcp_server/exporters/`

Responsibilities:

- Build SCORM package scaffolds.
- Later generate H5P, LiaScript, Moodle, and Canvas payloads.

## 5. Tool registration rule

All MCP tools must be registered from one place: `src/course_mcp_server/tools.py`.

Do not dynamically discover tools from arbitrary modules. Dynamic discovery can accidentally expose internal functions.

## 6. MCP exposed tools

The current production-facing tools are documented in `docs/tool-contracts.md`.

The intended flow is:

```text
create_course_project
-> ingest_course_source
-> generate_course_blueprint
-> generate_module_pack
-> generate_lesson_pack
-> generate_interactive_activity
-> generate_assessment_bank
-> validate_instructional_quality
-> build_export_package
-> request_publish_approval
```

`get_course_generation_status` and `list_course_artifacts` are read-only, tenant-scoped support tools.

## 7. Tools that must never be exposed

- shell execution
- arbitrary file read/write
- environment variable access
- database console/query access
- internal prompt dumping
- raw log dumping
- unrestricted web browsing
- direct Docker access
- private Git repository read access

## 8. Development workflow

```bash
./scripts/bootstrap.sh
pytest
ruff check .
docker compose up -d --build
curl http://localhost:8777/health
```

## 9. Production deployment steps

1. Create a new folder on the server, separate from the existing application.
2. Upload or clone this repository.
3. Copy `.env.example` to `.env`.
4. Write a strong token to `secrets/mcp_api_token.txt` and the OpenRouter key to `secrets/openrouter_api_key.txt` if used.
5. Build and run:

```bash
docker compose up -d --build
```

6. Confirm health:

```bash
curl http://localhost:8777/health
```

7. Add reverse proxy/TLS if exposing beyond localhost.
8. Add Codex configuration only after the endpoint is reachable.

## 10. Rollback

```bash
docker compose down
# checkout previous git tag or commit
git checkout <previous-good-commit>
docker compose up -d --build
```

## 11. Branching model

- `main`: production-ready
- `dev`: integration branch
- `feature/*`: feature branches
- `hotfix/*`: urgent production fixes

## 12. CI requirements

Every PR must pass:

- unit tests
- linting
- tool allowlist check
- dependency audit
- Docker build

## 13. Codex instructions

See `AGENTS.md`. Codex should modify only the files needed for requested implementation. Codex must not weaken security policies or add broad file/system tools.

## 14. Roadmap

### Sprint 1

- MCP skeleton
- tool contracts
- Docker deployment
- basic generation placeholders
- security allowlist

### Sprint 2

- real LLM integration
- source ingestion pipeline
- SCORM generator
- artifact persistence

### Sprint 3

- H5P generator
- LMS adapters
- human approval workflow
- audit UI

### Sprint 4

- tenant model
- role-based permissions
- analytics
- completion/certificate workflows
