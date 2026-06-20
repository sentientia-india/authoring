# Deployment Guide

## 1. Server assumption

You already have a server and one Docker instance running. This project should be deployed as a separate Docker service and not merged into the existing container.

## 2. Deploy in a new directory

```bash
mkdir -p /opt/samrat-course-mcp
cd /opt/samrat-course-mcp
```

Copy/clone the repository here.

## 3. Environment setup

```bash
cp .env.example .env
mkdir -p secrets
printf '%s\n' '<strong-random-token>' > secrets/mcp_api_token.txt
printf '%s\n' '<openrouter-api-key-or-empty>' > secrets/openrouter_api_key.txt
nano .env
```

Set:

```bash
MCP_HOST=0.0.0.0
MCP_PORT=8777
ENVIRONMENT=production
```

`MCP_API_TOKEN` and `OPENROUTER_API_KEY` should be provided through Compose secret files:

```text
secrets/mcp_api_token.txt
secrets/openrouter_api_key.txt
```

## 4. Build and run

```bash
docker compose up -d --build
```

## 5. Check status

```bash
docker compose ps
curl http://localhost:8777/health
curl http://localhost:8788/
```

The healthcheck must return HTTP 200 from `/health`; missing routes or connection failures now fail the container healthcheck.
The SCORM editor must return HTTP 200 from `/` and should show the authoring workspace.

From your browser, open the SCORM editor with the server IP or domain:

```text
http://<server-ip-or-domain>:8788/
```

The MCP service remains bound to server-local `127.0.0.1:8777` because it is an agent/tool endpoint, not a public web UI.

For a local Docker smoke test on Windows PowerShell, run:

```powershell
.\scripts\docker_smoke.ps1
```

## 6. Logs

```bash
docker compose logs -f course-mcp scorm-editor
```

## 7. Rollback

```bash
docker compose down
git checkout <previous-good-commit>
docker compose up -d --build
```

## 8. Reverse proxy

The SCORM editor is exposed on port `8788` for direct server testing. For production use, put it behind Nginx/Caddy/Traefik with TLS and rate limiting. Do not expose the MCP endpoint directly to the public internet.

## 9. Backup

Back up only artifact output and metadata DB after those are introduced. Do not back up `.env` into shared locations.

## 10. Production hardening

- Use Docker Compose secrets or a dedicated secrets manager for API tokens.
- Restrict inbound firewall to trusted IPs.
- Add reverse proxy auth if public.
- Enable dependency scanning.
- Monitor audit logs.
- Use versioned Docker images, not only `latest`.

## 11. GitHub Actions deployment

The repository includes `.github/workflows/deploy.yml`. It runs after the `CI` workflow succeeds on `main`, connects to the server by SSH, uploads the checked-out repository contents to the deployment path, writes a production `.env`, and runs:

```bash
docker compose up -d --build
```

Add these GitHub repository secrets before enabling production deployment:

```text
SERVER_HOST=<server-ip-or-domain>
SERVER_PORT=22
SERVER_USER=<ssh-user>
SERVER_SSH_KEY=<private-ssh-key-for-that-user>
DEPLOY_PATH=/opt/samrat-course-mcp
MCP_API_TOKEN=<strong-random-token-written-to-secrets/mcp_api_token.txt>
MCP_PORT=8777
OPENROUTER_API_KEY=<openrouter-api-key>
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

The server user must have permission to write to `DEPLOY_PATH` and run `docker compose`. The server does not need GitHub credentials because the workflow uploads the checked-out repository over SSH.
