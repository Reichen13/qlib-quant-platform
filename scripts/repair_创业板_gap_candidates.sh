#!/usr/bin/env bash
set -euo pipefail

# Run inside the quant-backend container.
# This writes only the selected Qlib feature files for known gap candidates.

CODES=(
  sz300024 sz300033 sz300058 sz300059 sz300070 sz300072
  sz300085 sz300122 sz300133 sz300136 sz300142 sz300144
  sz300146 sz300168 sz300182 sz300251 sz300296 sz300315
  sz300347 sz300408 sz300413 sz300498 sz300601 sz300628
)

for code in "${CODES[@]}"; do
  echo "=== Repairing ${code} ==="
  python /app/update_cn_data.py \
    --start 2026-04-30 \
    --end 2026-06-19 \
    --code "${code}" \
    --rebuild-stale
done

echo "=== Done ==="
