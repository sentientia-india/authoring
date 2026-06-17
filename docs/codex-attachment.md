# Attach Sentientia Course MCP to Codex

## 1. Local/project-scoped config

Use `.codex/config.example.toml` as the starting point. For trusted projects, create:

```text
.codex/config.toml
```

Example:

```toml
[mcp_servers.sentientiaCourseMcp]
url = "http://localhost:8777/mcp"

[mcp_servers.sentientiaCourseMcp.env]
MCP_API_TOKEN = "replace-with-token"
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
Use the Sentientia Course MCP to list available tools and generate a course outline for airline safety onboarding.
```

## 4. Important security note

Do not connect Codex to a broader file-system or shell MCP for this production server. The whole point is to expose only safe course-generation capability.
