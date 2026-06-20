#!/usr/bin/env bash
set -uo pipefail

# Read-only audit for the qlib quant platform server deployment.
# This script prints evidence only. It does not write files, restart services,
# change configs, or access projects outside the configured project directory.

PROJECT_DIR="${1:-$HOME/quant-platform}"
PUBLIC_URL="${PUBLIC_URL:-http://127.0.0.1:9090}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8001}"

section() {
  printf '\n===== %s =====\n' "$1"
}

run() {
  printf '\n$ %s\n' "$*"
  "$@" 2>&1 || true
}

section "Scope"
echo "project_dir=$PROJECT_DIR"
echo "public_url=$PUBLIC_URL"
echo "backend_url=$BACKEND_URL"
echo "user=$(id -un 2>/dev/null || true)"
echo "host=$(hostname 2>/dev/null || true)"
echo "time=$(date -Iseconds 2>/dev/null || true)"

section "Project Directory"
if [ -d "$PROJECT_DIR" ]; then
  run pwd
  run find "$PROJECT_DIR" -maxdepth 2 -type f \
    \( -name 'docker-compose.yml' -o -name 'Dockerfile.backend' -o -name 'data.py' -o -name 'api.ts' -o -name 'index.tsx' -o -name 'update_cn_data.py' \) \
    -printf '%TY-%Tm-%Td %TH:%TM %p\n'
  if [ -d "$PROJECT_DIR/.git" ]; then
    run git -C "$PROJECT_DIR" rev-parse --short HEAD
    run git -C "$PROJECT_DIR" status --short
    run git -C "$PROJECT_DIR" log --oneline -5
  else
    echo "git_status=not_a_git_worktree"
  fi
else
  echo "project_dir_missing"
fi

section "Key File Fingerprints"
for file in \
  "$PROJECT_DIR/backend/api/data.py" \
  "$PROJECT_DIR/frontend/src/lib/api.ts" \
  "$PROJECT_DIR/frontend/src/pages/data-management/index.tsx" \
  "$PROJECT_DIR/docker-compose.yml" \
  "$PROJECT_DIR/update_cn_data.py"; do
  if [ -f "$file" ]; then
    run sha256sum "$file"
    run wc -l "$file"
  else
    echo "missing $file"
  fi
done

section "Docker"
run docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
run docker stats --no-stream
run docker logs quant-backend --tail 120

section "System Resources"
run free -h
run df -h
run uptime

section "Qlib Data"
for QLIB_DIR in \
  "$HOME/.qlib/qlib_data/cn_data" \
  "/home/ubuntu/.qlib/qlib_data/cn_data" \
  "/root/.qlib/qlib_data/cn_data"; do
  if [ -d "$QLIB_DIR" ]; then
    echo "qlib_data_found=$QLIB_DIR"
    run find "$QLIB_DIR" -maxdepth 2 -type f \
      \( -path '*/calendars/day.txt' -o -path '*/instruments/csi300.txt' \) \
      -printf '%TY-%Tm-%Td %TH:%TM %p\n'
    if [ -f "$QLIB_DIR/calendars/day.txt" ]; then
      run tail -5 "$QLIB_DIR/calendars/day.txt"
    fi
  else
    echo "qlib_data_missing=$QLIB_DIR"
  fi
done

section "Nginx"
run nginx -t
run systemctl is-active nginx
run ls -l /etc/nginx/sites-enabled

section "HTTP Probes"
for url in \
  "$BACKEND_URL/health" \
  "$BACKEND_URL/api/data/health" \
  "$PUBLIC_URL/health" \
  "$PUBLIC_URL/api/data/health"; do
  printf '\n$ curl %s\n' "$url"
  curl -sS --max-time 20 -w '\nHTTP_STATUS=%{http_code} TIME_TOTAL=%{time_total}\n' "$url" || true
done
