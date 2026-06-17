# Deployment Guide

## 1. Server assumption

You already have a server and one Docker instance running. This project should be deployed as a separate Docker service and not merged into the existing container.

## 2. Deploy in a new directory

```bash
mkdir -p /opt/sentientia-course-mcp
cd /opt/sentientia-course-mcp
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
