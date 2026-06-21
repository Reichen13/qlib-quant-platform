#!/usr/bin/env bash
set -euo pipefail

# Safe deploy helper for the qlib quant platform fixes.
#
# Default mode is preflight only. It prints current state and exits without
# changing files, containers, data, or Nginx.
#
# To actually deploy, run from the server:
#   APPLY=1 bash scripts/deploy_current_fixes.sh /path/to/project
#
# Scope:
# - project git worktree
# - backend container managed by this project's docker compose file
# - frontend static directory configured by STATIC_DIR
# - Qlib data directory backup only; this script does not repair data

PROJECT_DIR="${1:-$HOME/quant-platform}"
STATIC_DIR="${STATIC_DIR:-/var/www/quant}"
QLIB_DIR="${QLIB_DIR:-$HOME/.qlib/qlib_data/cn_data}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8001}"
PUBLIC_URL="${PUBLIC_URL:-http://49.235.215.39:9090}"
TARGET_BRANCH="${TARGET_BRANCH:-main}"
APPLY="${APPLY:-0}"

section() {
  printf '\n===== %s =====\n' "$1"
}

run() {
  printf '\n$ %s\n' "$*"
  "$@"
}

run_allow_fail() {
  printf '\n$ %s\n' "$*"
  "$@" || true
}

abort() {
  echo "ERROR: $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || abort "missing command: $1"
}

need_cmd git
need_cmd curl
need_cmd docker
need_cmd npm

section "Scope"
echo "project_dir=$PROJECT_DIR"
echo "static_dir=$STATIC_DIR"
echo "qlib_dir=$QLIB_DIR"
echo "backend_url=$BACKEND_URL"
echo "public_url=$PUBLIC_URL"
echo "target_branch=$TARGET_BRANCH"
echo "apply=$APPLY"
echo "time=$(date -Iseconds 2>/dev/null || true)"

[ -d "$PROJECT_DIR" ] || abort "project directory does not exist: $PROJECT_DIR"
[ -f "$PROJECT_DIR/docker-compose.yml" ] || abort "missing docker-compose.yml under $PROJECT_DIR"
[ -f "$PROJECT_DIR/update_cn_data.py" ] || abort "missing update_cn_data.py under $PROJECT_DIR"
[ -d "$PROJECT_DIR/frontend" ] || abort "missing frontend directory under $PROJECT_DIR"
[ -d "$PROJECT_DIR/.git" ] || abort "project directory is not a git worktree: $PROJECT_DIR"

section "Preflight"
run git -C "$PROJECT_DIR" status -sb
run git -C "$PROJECT_DIR" log --oneline -3
run_allow_fail docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
run_allow_fail curl -sS --max-time 20 "$BACKEND_URL/health"
echo
run_allow_fail curl -sS --max-time 30 "$BACKEND_URL/api/data/health"
echo

if [ "$APPLY" != "1" ]; then
  section "Dry run complete"
  echo "No changes were made. Re-run with APPLY=1 to deploy after reviewing the preflight output."
  exit 0
fi

section "Safety checks"
if [ -n "$(git -C "$PROJECT_DIR" status --porcelain)" ]; then
  git -C "$PROJECT_DIR" status --short
  abort "server worktree has uncommitted changes; stop and compare before deploying"
fi

ts="$(date +%Y%m%d-%H%M%S)"
project_backup="${PROJECT_DIR}.bak-${ts}"
static_backup="${STATIC_DIR}.bak-${ts}"
qlib_backup="${QLIB_DIR}.bak-${ts}"

section "Backups"
run cp -a "$PROJECT_DIR" "$project_backup"
if [ -d "$STATIC_DIR" ]; then
  run sudo cp -a "$STATIC_DIR" "$static_backup"
else
  echo "static_dir_missing=$STATIC_DIR"
fi
if [ -d "$QLIB_DIR" ]; then
  run cp -a "$QLIB_DIR" "$qlib_backup"
else
  echo "qlib_dir_missing=$QLIB_DIR"
fi

section "Update code"
run git -C "$PROJECT_DIR" fetch origin
run git -C "$PROJECT_DIR" checkout "$TARGET_BRANCH"
run git -C "$PROJECT_DIR" pull --ff-only origin "$TARGET_BRANCH"
run git -C "$PROJECT_DIR" log --oneline -3

section "Deploy backend"
run docker compose -f "$PROJECT_DIR/docker-compose.yml" build backend
run docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d backend
run docker compose -f "$PROJECT_DIR/docker-compose.yml" logs --tail=120 backend
run curl -sS --max-time 20 "$BACKEND_URL/health"
echo

section "Deploy frontend"
run npm --prefix "$PROJECT_DIR/frontend" install --legacy-peer-deps
run npm --prefix "$PROJECT_DIR/frontend" run build
if [ -d "$STATIC_DIR" ]; then
  run sudo cp -r "$PROJECT_DIR/frontend/dist/." "$STATIC_DIR/"
  run sudo chown -R www-data:www-data "$STATIC_DIR"
else
  echo "static_dir_missing=$STATIC_DIR"
  echo "frontend build completed but static files were not copied"
fi

section "Post-deploy verification"
if [ -f "$PROJECT_DIR/scripts/verify_current_fixes.sh" ]; then
  BACKEND_URL="$BACKEND_URL" PUBLIC_URL="$PUBLIC_URL" bash "$PROJECT_DIR/scripts/verify_current_fixes.sh"
else
  echo "missing verify_current_fixes.sh"
fi

section "Done"
echo "project_backup=$project_backup"
echo "static_backup=$static_backup"
echo "qlib_backup=$qlib_backup"

