# Attach Samrat Course MCP to Codex

## 1. Local/project-scoped config

Use `.codex/config.example.toml` as the starting point. For trusted projects, create:

```text
.codex/config.toml
```

Example:

```toml
[mcp_servers.samrat-course-mcp]
url = "http://127.0.0.1:8777/mcp"
transport = "http"

[mcp_servers.samrat-course-mcp.headers]
authorization = "Bearer replace-with-token"
```

## 2. Codex working rules

Keep `AGENTS.md` in the repository root. It tells Codex:

- use only the course MCP for course-generation tasks
- do not add unsafe tools
- do not touch secrets
- preserve Docker isolation
- add tests when modifying tools

## 3. Verification

```bash
codex mcp list
```

Then ask Codex:

```text
Use the Samrat Course MCP to create a course project for airline safety onboarding and generate a course blueprint.
```

## 4. Important security note

Do not connect Codex to a broader file-system or shell MCP for this production server. The whole point is to expose only safe course-generation capability.
