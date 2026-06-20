# Service Split: MCP and SCORM Editor

This repository contains two product surfaces that deploy together from GitHub but run as separate server processes.

## 1. MCP Service

Path: `src/course_mcp_server/`

Purpose:
- course discovery workflow
- source ingestion orchestration
- Codex/generation-agent handoff
- instructional quality validation
- SCORM/export packaging
- safe MCP tool surface

Rules:
- no shell, arbitrary file, environment, database, Docker, raw log, source-code, or prompt tools
- no browser-based drag-and-drop authoring inside MCP
- no direct learner editing UI inside MCP
- MCP returns artifacts and metadata only

Deployment:
- Docker service name: `course-mcp`
- default local port: `127.0.0.1:8777`
- health route: `/health`

## 2. SCORM Editor App

Path: `apps/scorm_editor/`

Purpose:
- upload/import an exported SCORM zip
- inspect manifest and course JSON
- edit learner-facing text, section order, activities, theme tokens, and quiz copy
- preview desktop/tablet/mobile learner views
- re-export a valid SCORM zip

Rules:
- runs as a separate web app/service
- never becomes an MCP tool
- never receives MCP secrets
- does not expose server filesystem browsing
- edits only uploaded/imported course artifacts inside its own workspace
- browser-only drag/drop editing is allowed
- SCORM import/export stays zip-based and does not depend on H5P packaging

Deployment:
- Docker service name: `scorm-editor`
- default local port: `127.0.0.1:8788`
- health route: `/`

## Why One GitHub Repo Still Works

One repo is fine because CI can build and deploy both services from the same commit. The services must stay separate at runtime:

```text
GitHub repository
|-- src/course_mcp_server/        # secure MCP generation/export service
|-- apps/scorm_editor/            # separate visual editor app
|-- docker-compose.yml            # independent services
`-- docs/                         # shared contracts and runbooks
```

This lets the backend generate a strong first SCORM export while the editor app gives a human a safe place to polish the remaining details.
