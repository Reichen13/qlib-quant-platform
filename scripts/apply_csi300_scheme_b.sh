#!/usr/bin/env bash
set -euo pipefail

candidate="/tmp/csi300.remove-stale-dedupe.txt"
target="/home/ubuntu/.qlib/qlib_data/cn_data/instruments/csi300.txt"

rows="$(grep -cve '^$' "$candidate")"
unique="$(awk -F '\t' 'NF { print tolower($1) }' "$candidate" | sort -u | wc -l | tr -d ' ')"

echo "candidate_rows=${rows}"
echo "candidate_unique=${unique}"

if [[ "$rows" != "653" || "$unique" != "653" ]]; then
  echo "Candidate validation failed; expected rows=653 and unique=653" >&2
  exit 1
fi

ts="$(date +%Y%m%d-%H%M%S)"
backup="${target}.bak-scheme-b-${ts}"
cp "$target" "$backup"
cp "$candidate" "$target"

echo "backup=${backup}"
wc -l "$target"
