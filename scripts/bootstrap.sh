#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp -n .env.example .env || true

echo "Bootstrap complete. Edit .env, then run: docker compose up -d --build"
