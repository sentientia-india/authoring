#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: ./scripts/push_to_github.sh git@github.com:ORG/REPO.git"
  exit 1
fi

REMOTE_URL="$1"

git init
if ! git branch --show-current | grep -q '^main$'; then
  git checkout -b main
fi

git add .
git commit -m "Initial Sentientia Course MCP project"
git remote add origin "$REMOTE_URL" 2>/dev/null || git remote set-url origin "$REMOTE_URL"
git push -u origin main
