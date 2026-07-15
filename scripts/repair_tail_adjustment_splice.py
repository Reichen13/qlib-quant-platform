#!/usr/bin/env python
"""Repair tail adjustment-splice pollution via Baostock overwrite rebuild.

Reads a code list (from scan_tail_adjustment_splice.py) and invokes
update_cn_data.py with --rebuild-stale --overwrite-existing so trailing
placeholder-factor / forward-price rows are rewritten to the canonical
raw×backAdjustFactor storage.

Usage:
  python scripts/scan_tail_adjustment_splice.py --out ~/.qlib/cache/tail_splice_codes.txt
  python scripts/repair_tail_adjustment_splice.py --codes-file ~/.qlib/cache/tail_splice_codes.txt
  python scripts/repair_tail_adjustment_splice.py --code sh600519 --start 2024-01-01
  python scripts/repair_tail_adjustment_splice.py --codes-file ... --max 20   # dry sample
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = ROOT / "update_cn_data.py"


def _load_codes(args: argparse.Namespace) -> list[str]:
    codes: list[str] = []
    if args.code:
        codes.extend(args.code)
    if args.codes_file:
        path = Path(args.codes_file).expanduser()
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            codes.append(line)
    # normalize to qlib lower form sh600519
    out: list[str] = []
    seen = set()
    for raw in codes:
        c = raw.strip().lower().replace(".ss", "").replace(".sz", "").replace(".bj", "")
        if c.startswith(("sh", "sz", "bj")):
            code = c
        elif c.isdigit() and len(c) == 6:
            if c.startswith(("5", "6", "9")):
                code = "sh" + c
            else:
                code = "sz" + c
        else:
            code = c
        if code not in seen:
            seen.add(code)
            out.append(code)
    if args.max:
        out = out[: args.max]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair tail splice via Baostock overwrite")
    parser.add_argument("--code", action="append", default=[], help="Single code, repeatable")
    parser.add_argument("--codes-file", default="", help="Text file with one code per line")
    parser.add_argument("--start", default="2024-01-01", help="Rebuild window start")
    parser.add_argument("--end", default="", help="Rebuild window end (default today)")
    parser.add_argument("--max", type=int, default=0, help="Only first N codes")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    codes = _load_codes(args)
    if not codes:
        print("ERROR: no codes provided. Use --code or --codes-file")
        return 2
    if not UPDATE_SCRIPT.exists():
        print(f"ERROR: missing {UPDATE_SCRIPT}")
        return 3

    print(f"repairing {len(codes)} stocks from {args.start} (baostock overwrite)")
    if args.dry_run:
        print("dry-run codes:", ", ".join(codes[:20]), ("..." if len(codes) > 20 else ""))
        return 0

    # Batch to avoid huge command lines on Windows
    batch_size = 50
    failures = 0
    for i in range(0, len(codes), batch_size):
        batch = codes[i : i + batch_size]
        cmd = [
            sys.executable,
            str(UPDATE_SCRIPT),
            "--start",
            args.start,
            "--rebuild-stale",
            "--overwrite-existing",
        ]
        if args.end:
            cmd.extend(["--end", args.end])
        for code in batch:
            cmd.extend(["--code", code])
        print(f"\n=== batch {i // batch_size + 1}: {len(batch)} codes ===")
        print(" ", " ".join(cmd[:8]), f"... ({len(batch)} --code)")
        proc = subprocess.run(cmd, cwd=str(ROOT))
        if proc.returncode != 0:
            failures += 1
            print(f"WARN: batch exit code {proc.returncode}")

    # Invalidate trust cache after repair
    try:
        sys.path.insert(0, str(ROOT / "backend"))
        from core.data_trust import invalidate_data_trust_cache

        invalidate_data_trust_cache()
        print("data_trust cache invalidated")
    except Exception as e:
        print(f"WARN: could not invalidate trust cache: {e}")

    print(f"\ndone. failed_batches={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
