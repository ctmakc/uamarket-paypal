#!/usr/bin/env bash
# Deploy (or update) the public demo from a pushed commit.
#
#   scripts/demo_deploy.sh [git-ref]     default ref: origin/main
#
# The stack runs from its own worktree (DEMO_DIR, default /data/projects/uamarket-demo), so edits in
# the development checkout never reach the demo until they are pushed and this script runs again.
# The default ref is origin/main: the demo deployed from the feature branch until 17.09.2026,
# which let the public site and main drift apart silently. Everything the branch carried is merged
# into main, so main is the only thing the demo follows.
# Settings and secrets: DEMO_ENV (default ~/.config/uamarket/demo.env, mode 600, never committed).
# Runbook: docs/DEMO-DEPLOY.md.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
REF="${1:-origin/main}"
DEMO_DIR="${DEMO_DIR:-/data/projects/uamarket-demo}"
DEMO_ENV="${DEMO_ENV:-$HOME/.config/uamarket/demo.env}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-uamarket-demo}"

[ -r "$DEMO_ENV" ] || { echo "missing $DEMO_ENV (docs/DEMO-DEPLOY.md, step 1)" >&2; exit 2; }

git -C "$REPO" fetch --quiet origin
if [ ! -d "$DEMO_DIR/.git" ] && [ ! -f "$DEMO_DIR/.git" ]; then
  git -C "$REPO" worktree add --detach "$DEMO_DIR" "$REF"
else
  git -C "$DEMO_DIR" checkout --quiet --detach "$REF"
fi
echo "demo at $(git -C "$DEMO_DIR" log --oneline -1)"

cd "$DEMO_DIR"
P=(docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.tunnel.yml --env-file "$DEMO_ENV")
"${P[@]}" config -q
"${P[@]}" up -d --build --wait --wait-timeout 300
"${P[@]}" ps --format 'table {{.Service}}\t{{.Status}}'
