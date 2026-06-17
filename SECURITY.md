# Security Model: Sentientia Course MCP

## 1. Security goal

Codex and MCP clients must be able to request course-generation work without seeing or controlling the private internals of the project.

The MCP server exposes a **capability boundary**. It does not expose the application source code, prompts, secrets, database, file system, shell, Docker socket, or admin operations.

## 2. Threat model

### Threats

1. Prompt injection through source training content.
2. Tool poisoning through misleading MCP tool descriptions.
3. Excessive agency: agent attempts actions beyond intended scope.
4. Secret leakage through logs or tool outputs.
5. Arbitrary file access.
6. Shell command execution.
7. Database exfiltration.
8. Container breakout due to privileged mounts.
9. Cross-tenant data leakage.
10. Supply-chain risk from open-source packages.

### Protected assets

- internal prompts
- customer training documents
- course-generation pipeline
- source code
- environment variables
- API keys
- LMS credentials
- learner records
- generated course IP
- production server filesystem

## 3. Security controls

### 3.1 MCP tool allowlist

Only explicitly registered course tools are visible to Codex.

Allowed MVP tools:

- `generate_course_outline`
- `generate_lesson_draft`
- `generate_quiz_bank`
- `generate_roleplay_scenario`
- `validate_course_schema`
- `build_scorm_package_scaffold`
- `get_course_generation_status`

Denied tool classes:

- shell
- filesystem
- environment
- database
- Docker
- raw HTTP fetch
- admin console
- prompt dump

### 3.2 Tool-level authorization

Each tool call must pass:

1. token validation
2. tenant validation
3. tool permission check
4. input schema validation
5. output redaction
6. audit logging

### 3.3 Data minimization

The MCP output should return only the generated artifact or status needed by the caller. It must not return internal chain logs, raw prompt templates, stack traces, absolute paths, database rows, or secret values.

### 3.4 Prompt injection protection

Untrusted course source material is treated as content, not instruction. The generation service must separate:

- system/developer instructions
- trusted configuration
- untrusted user/source material
- output schema

### 3.5 Container hardening

Docker deployment must use:

- non-root user
- no Docker socket mount
- no privileged mode
- read-only root filesystem where possible
- limited writable tmpfs/output folders
- isolated Docker network
- resource limits
- minimal base image
- healthcheck

### 3.6 Network hardening

Default deployment exposes only localhost port `8777`. Put it behind reverse proxy/TLS if remote access is required. Outbound network access should be restricted to approved APIs only.

### 3.7 Secrets handling

Secrets go only in `.env` or server secret manager. They must never be committed, logged, or returned to MCP clients.

### 3.8 Audit logging

Each MCP call logs:

- request ID
- timestamp
- tenant ID
- user ID
- tool name
- policy decision
- input hash
- output hash
- latency
- approval requirement

Do not log full source documents or secrets.

### 3.9 Human approval gates

The following actions require human approval:

- publishing to LMS
- deleting courses
- overwriting published courses
- sending learner messages
- exporting customer-owned source data
- changing security config

## 4. Secure coding rules for Codex

Codex must not:

- add arbitrary file tools
- add shell execution tools
- bypass authorization
- disable audit logging
- return raw environment variables
- expose internal prompts
- weaken Docker security settings
- commit `.env`

Codex may:

- add new course-generation tools only if they are schema-defined and added to the allowlist intentionally
- add tests for security policies
- improve validation and redaction
- improve export modules
- improve documentation

## 5. Production checklist

- [ ] Strong API token set
- [ ] `.env` not committed
- [ ] Docker runs as non-root
- [ ] No Docker socket mounted
- [ ] No project source mounted read-write in production
- [ ] Tool allowlist test passes
- [ ] Secret redaction test passes
- [ ] Dependency audit passes
- [ ] TLS enabled if public
- [ ] Reverse proxy rate limits enabled if public
- [ ] Backup and rollback documented
