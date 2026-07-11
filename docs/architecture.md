# Architecture: Samrat Course MCP

Hosted learner delivery, Stripe webhook processing and the public landing/editor routes are transport services, not MCP tools. They cannot register themselves in `TOOL_REGISTRY`; this preserves the course-tool allowlist and keeps learner traffic separate from agent authorization.

## Target architecture

```text
+-------------------+       +--------------------------+
| Codex / MCP Host  | ----> | Samrat Course MCP        |
+-------------------+       | Docker container         |
                            +------------+-------------+
                                         |
                            +------------v-------------+
                            | Auth + Tool Policy Layer |
                            +------------+-------------+
                                         |
                            +------------v-------------+
                            | Allowlisted Course Tools |
                            +------------+-------------+
                                         |
              +--------------------------+--------------------------+
              |                          |                          |
+-------------v-------------+ +----------v----------+ +-------------v-------------+
| Course Generation Service | | Export Service      | | LMS Adapter Service       |
| internal generation logic  | | SCORM/H5P runtime   | | Moodle/Canvas/custom LMS  |
+---------------------------+ +---------------------+ +---------------------------+
```

## Why separate Docker instance

The MCP server should not run inside the existing app container because it introduces a new agent-accessible interface. Separate deployment reduces blast radius, allows independent scaling, and makes security policy easier to enforce.

## Trust boundary

Codex is trusted to request work, not trusted to inspect internals.

Codex can call:

- material ticket intake
- chapter layout planning
- course project creation
- template selection
- source ingestion
- blueprint, module, lesson, activity, and assessment generation
- interactive video generation
- instructional and superior quality validation
- export package generation

Codex cannot call:

- source code file read
- shell command execution
- environment dump
- database query
- prompt dump
- Docker control

## Data flow

1. Client authenticates to MCP endpoint.
2. Client calls an allowlisted tool.
3. Request is validated using schema.
4. Authorization layer approves or denies.
5. Internal service generates structured artifact.
6. Output redactor removes secrets/internal paths.
7. Audit event is written.
8. MCP returns safe output.

## Deployment topology

```text
Existing app container        Course MCP container
----------------------        --------------------
main LMS/API                  isolated MCP service
existing Docker network       dedicated course-mcp-net
existing DB access            no DB access in MVP
public app port               localhost/private MCP port
```

## Future production topology

```text
Reverse Proxy / TLS
        |
        v
MCP Gateway / Auth
        |
        v
Course MCP Service
        |
        |-- Redis queue
        |-- Postgres metadata DB
        |-- S3-compatible artifact store
        `-- LMS adapters
```

## Production Internals Added

- Docker Compose provisions internal Postgres and Redis services on the private MCP network.
- The application has JSON fallback storage for local development and test runs.
- Audit events are persisted as hashed metadata, not raw prompts/source payloads.
- Per-tenant/user rate limiting runs before tool execution.
- Exported package responses include artifact metadata URIs instead of exposing arbitrary file browsing.
