#!/usr/bin/env bash
set -euo pipefail

# Verify the 2026-06-21 fixes after deployment.
# This script only probes HTTP endpoints and writes temporary files under /tmp.
# It does not update Qlib data, restart services, or modify project files.

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8001}"
PUBLIC_URL="${PUBLIC_URL:-http://49.235.215.39:9090}"
QUOTE_CODE="${QUOTE_CODE:-600519}"

section() {
  printf '\n===== %s =====\n' "$1"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing_command=$1"
    exit 2
  fi
}

need_cmd curl
need_cmd python3

section "Scope"
echo "backend_url=$BACKEND_URL"
echo "public_url=$PUBLIC_URL"
echo "quote_code=$QUOTE_CODE"
echo "time=$(date -Iseconds 2>/dev/null || true)"

section "Health"
curl -sS --max-time 20 -w '\nHTTP_STATUS=%{http_code} TIME_TOTAL=%{time_total}\n' "$BACKEND_URL/health"
curl -sS --max-time 30 -w '\nHTTP_STATUS=%{http_code} TIME_TOTAL=%{time_total}\n' "$BACKEND_URL/api/data/health"

section "Quote zero OHLC audit"
quote_file="/tmp/quote-${QUOTE_CODE}.json"
curl -sS --max-time 30 "$BACKEND_URL/api/quote/${QUOTE_CODE}?frequency=daily&indicators=true" > "$quote_file"
python3 - "$quote_file" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    payload = json.load(f)

rows = payload.get("data") or []
valid = [
    r for r in rows
    if sum(abs(float(r.get(k) or 0)) for k in ("open", "high", "low", "close")) > 0
]
zero_count = len(rows) - len(valid)
summary = {
    "code": payload.get("code"),
    "total": len(rows),
    "zero_ohlc_count": zero_count,
    "first": rows[0].get("date") if rows else None,
    "first_valid": valid[0].get("date") if valid else None,
    "last": rows[-1].get("date") if rows else None,
}
print(summary)
if zero_count:
    print("QUOTE_ZERO_OHLC_PRESENT")
else:
    print("QUOTE_ZERO_OHLC_CLEAN")
PY

section "Factor async submit"
factor_file="/tmp/factor-submit.json"
cat > "$factor_file" <<'JSON'
{"start_date":"2026-01-01","end_date":"2026-04-30","predict_period":5,"top_k":20}
JSON

submit_file="/tmp/factor-submit-response.json"
curl -sS --max-time 20 \
  -X POST "$BACKEND_URL/api/factors/analyze/submit" \
  -H 'Content-Type: application/json' \
  --data-binary @"$factor_file" > "$submit_file"

cat "$submit_file"
echo

task_id="$(python3 - "$submit_file" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as f:
        payload = json.load(f)
    print(payload.get("task_id") or "")
except Exception:
    print("")
PY
)"

if [ -z "$task_id" ]; then
  echo "FACTOR_SUBMIT_NO_TASK_ID"
  exit 3
fi

echo "task_id=$task_id"
curl -sS --max-time 20 "$BACKEND_URL/api/factors/analyze/status/$task_id"
echo
echo "FACTOR_ASYNC_SUBMIT_OK"

section "Public URL smoke"
curl -sS --max-time 20 -I "$PUBLIC_URL/" | sed -n '1,10p'

