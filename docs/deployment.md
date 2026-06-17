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
nano .env
```

Set:

```bash
MCP_API_TOKEN=<strong-random-token>
MCP_HOST=0.0.0.0
MCP_PORT=8777
ENVIRONMENT=production
```

## 4. Build and run

```bash
docker compose up -d --build
```

## 5. Check status

```bash
docker compose ps
curl http://localhost:8777/health
```

## 6. Logs

```bash
docker compose logs -f course-mcp
```

## 7. Rollback

```bash
docker compose down
git checkout <previous-good-commit>
docker compose up -d --build
```

## 8. Reverse proxy

If exposing remotely, put the service behind Nginx/Caddy/Traefik with TLS and rate limiting. Do not expose the container directly to the public internet without auth and TLS.

## 9. Backup

Back up only artifact output and metadata DB after those are introduced. Do not back up `.env` into shared locations.

## 10. Production hardening

- Use a secrets manager if possible.
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
MCP_API_TOKEN=<strong-random-token>
MCP_PORT=8777
```

The server user must have permission to write to `DEPLOY_PATH` and run `docker compose`. The server does not need GitHub credentials because the workflow uploads the checked-out repository over SSH.
