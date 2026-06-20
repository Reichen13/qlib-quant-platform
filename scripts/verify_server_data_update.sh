#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/quant-platform

python3 - <<'PY'
import json
from pathlib import Path

Path("/tmp/update-one.json").write_text(
    json.dumps({"type": "stocks", "max_stocks": 1}),
    encoding="utf-8",
)
PY

echo "===== json ====="
cat /tmp/update-one.json
echo

echo "===== unauth update should fail ====="
curl -sS -i --max-time 20 \
  -X POST http://127.0.0.1:8001/api/data/update \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/update-one.json |
  sed -n '1,16p'

echo "===== authenticated tiny update start ====="
KEY=$(awk -F= '/^API_KEY=/{print $2; exit}' .env)
curl -sS -i --max-time 30 \
  -X POST http://127.0.0.1:8001/api/data/update \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${KEY}" \
  --data-binary @/tmp/update-one.json |
  tee /tmp/update-response.txt |
  sed -n '1,28p'
