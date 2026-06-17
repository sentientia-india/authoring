#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp -n .env.example .env || true
mkdir -p secrets
touch secrets/openrouter_api_key.txt
if [ ! -s secrets/mcp_api_token.txt ]; then
  python - <<'PY' > secrets/mcp_api_token.txt
import secrets
print(secrets.token_urlsafe(32))
PY
fi

echo "Bootstrap complete. Edit .env and secrets/*, then run: docker compose up -d --build"
