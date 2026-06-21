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

section "Fast market-data endpoints"
etf_file="/tmp/etf-signals.json"
curl -sS --max-time 12 -w '\nHTTP_STATUS=%{http_code} TIME_TOTAL=%{time_total}\n' \
  "$BACKEND_URL/api/etf/signals?days=20" > "$etf_file"
cat "$etf_file" | tail -n 1
python3 - "$etf_file" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    raw = f.read()
payload = json.loads(raw.split("\nHTTP_STATUS=", 1)[0])
print({
    "etf_count": len(payload.get("etfs") or []),
    "warning": payload.get("warning"),
})
print("ETF_SIGNALS_FAST_OK")
PY

pair_file="/tmp/pair-list.json"
curl -sS --max-time 12 -w '\nHTTP_STATUS=%{http_code} TIME_TOTAL=%{time_total}\n' \
  "$BACKEND_URL/api/pair/list" > "$pair_file"
cat "$pair_file" | tail -n 1
python3 - "$pair_file" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    raw = f.read()
payload = json.loads(raw.split("\nHTTP_STATUS=", 1)[0])
pairs = payload.get("pairs") or []
first = pairs[0] if pairs else {}
print({
    "pair_total": payload.get("total"),
    "first_data_status": first.get("data_status"),
    "first_signal": first.get("signal"),
    "first_warning": first.get("warning"),
})
print("PAIR_LIST_FAST_OK")
PY

section "Public URL smoke"
curl -sS --max-time 20 -I "$PUBLIC_URL/" | sed -n '1,10p'

section "Frontend bundle version check"
index_file="/tmp/quant-public-index.html"
bundle_file="/tmp/quant-public-bundle.js"
curl -sS --max-time 20 "$PUBLIC_URL/" > "$index_file"
asset_path="$(python3 - "$index_file" <<'PY'
import re
import sys

html = open(sys.argv[1], encoding="utf-8", errors="replace").read()
match = re.search(r'<script[^>]+src="([^"]+/assets/[^"]+\.js)"', html)
print(match.group(1) if match else "")
PY
)"

if [ -z "$asset_path" ]; then
  echo "FRONTEND_BUNDLE_ASSET_NOT_FOUND"
  exit 4
fi

case "$asset_path" in
  http*) bundle_url="$asset_path" ;;
  *) bundle_url="${PUBLIC_URL%/}$asset_path" ;;
esac

echo "bundle_url=$bundle_url"
curl -sS --max-time 30 "$bundle_url" > "$bundle_file"
python3 - "$bundle_file" <<'PY'
import sys

bundle = open(sys.argv[1], encoding="utf-8", errors="replace").read()
needles = [
    "去数据管理配置 Key",
    "ETF/指数暂按 Qlib 状态代理展示",
    "指定股票代码",
]
missing = [needle for needle in needles if needle not in bundle]
if missing:
    print({"missing_frontend_copy": missing})
    print("FRONTEND_BUNDLE_COPY_MISSING")
    sys.exit(5)
print("FRONTEND_BUNDLE_COPY_OK")
PY
