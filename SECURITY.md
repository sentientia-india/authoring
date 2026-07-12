# Security policy

Please do not disclose suspected vulnerabilities publicly. Use GitHub private vulnerability reporting for this repository, including affected version, reproducible steps, impact, and any suggested mitigation.

Do not include customer course material, learner information, credentials, access tokens, or production database contents in a report. Redact them and use synthetic evidence.

We acknowledge credible reports, preserve evidence, assess tenant impact, rotate affected credentials, remediate, verify, and communicate according to severity. Suspected cross-tenant access, data loss, billing corruption, authentication bypass, or critical upload/generated-content vulnerabilities are stop-ship incidents.

Supported security fixes apply to the current production release. Older releases may be retired when a security upgrade is available.

## Security goal

Codex and MCP clients must be able to request course-generation work without seeing or controlling the private internals of the project.

The MCP server exposes a capability boundary. It does not expose the application source code, prompts, secrets, database, file system, shell, Docker socket, or admin operations.

## Threats and protected assets

Threats include prompt injection through source content, tool poisoning, excessive agency, secret leakage, arbitrary file or shell access, database exfiltration, container breakout, cross-tenant disclosure, generated-content attacks, forged webhooks, billing corruption, and supply-chain compromise.

Protected assets include internal prompts, customer documents, course-generation logic, source code, environment variables, API/LMS/payment/email credentials, learner records, generated course IP, billing and entitlement state, audit evidence, and the production filesystem.

## Security controls

### MCP tool allowlist

Only explicitly registered course tools are visible to clients. Allowed tools are the lifecycle tools listed in `docs/tool-contracts.md`. Shell, arbitrary filesystem, environment, database, Docker, raw HTTP fetch, admin console, and prompt-dump tool classes are denied.

### Tool authorization

Each tool call passes token validation, tenant validation, permission checks, schema validation, output redaction, rate limiting, and audit logging.

### Data minimization

Outputs contain only the artifact or status required by the caller. They do not return internal chain logs, raw prompts, stack traces, absolute paths, database rows, credentials, or secret values.

### Prompt-injection protection

Untrusted course material is content, not instruction. Generation separates system/developer instructions, trusted configuration, untrusted source material, and output schemas.

### Container hardening

Production containers use non-root users, no Docker socket, no privileged mode, read-only roots where possible, bounded writable tmpfs/output storage, isolated networks, dropped capabilities, `no-new-privileges`, minimal images, and health checks.

### Network and browser hardening

The MCP binds to localhost by default. Public deployments require TLS, restrictive proxy routes, authentication, rate limits, CSP/security headers, and explicit hosted/embed origins. Outbound access is limited to approved model, payment, email, object-storage, and LMS providers.

### Secret handling

Production secrets use Compose secret files or a server secret manager. `.env` contains non-secret configuration only where possible. Secrets are never committed, logged, placed in URLs, returned to clients, or copied into audit/analytics events.

### Audit logging

Each privileged action records request ID, timestamp, tenant, actor, action/tool, policy decision, target, hashes, result, latency, and approval requirement. Full source documents and secrets are excluded.

### Human approval gates

Publishing to an external LMS, deleting customer data, overwriting a published course, sending bulk learner messages, exporting customer-owned source data, changing security configuration, and privileged support access require explicit authorization.

## Secure coding rules

Contributors and coding agents must not add arbitrary file/shell/database tools, bypass authorization, disable auditing, expose environment variables or prompts, weaken Docker isolation, commit credentials, or dynamically expose every function as an MCP tool.

New MCP tools must be schema-defined, intentionally allowlisted, documented in `docs/tool-contracts.md`, security-tested, and return redacted structured output.

## Production checklist

- [ ] Strong API and webhook credentials configured and rotated.
- [ ] `.env` and secret files excluded from version control.
- [ ] Containers run non-root without Docker socket or privileged mounts.
- [ ] Tool allowlist, tenant isolation, redaction, static scan, dependency audit, and container scan pass.
- [ ] Public TLS, proxy rate limits, security headers, and domain ownership verified.
- [ ] PostgreSQL/object-store backups and clean restore drill pass RPO/RTO.
- [ ] Immutable deployment health promotion and rollback verified.
- [ ] Billing reconciliation has zero unexplained differences.
- [ ] Email sending domain and bounce/complaint suppression verified.
- [ ] Threat-model stop-ship findings resolved.
- [ ] Independent penetration test critical/high findings resolved.
