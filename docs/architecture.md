# Architecture: Sentientia Course MCP

## Target architecture

```text
+-------------------+       +--------------------------+
| Codex / MCP Host  | ----> | Sentientia Course MCP    |
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
| private prompts/pipeline  | | SCORM/H5P scaffold  | | Moodle/Canvas/custom LMS  |
+---------------------------+ +---------------------+ +---------------------------+
```

## Why separate Docker instance

The MCP server should not run inside the existing app container because it introduces a new agent-accessible interface. Separate deployment reduces blast radius, allows independent scaling, and makes security policy easier to enforce.

## Trust boundary

Codex is trusted to request work, not trusted to inspect internals.

Codex can call:

- course outline generation
- lesson generation
- quiz generation
- schema validation
- export scaffold generation

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
        │
        ▼
MCP Gateway / Auth
        │
        ▼
Course MCP Service
        │
        ├── Redis queue
        ├── Postgres metadata DB
        ├── S3-compatible artifact store
        └── LMS adapters
```
