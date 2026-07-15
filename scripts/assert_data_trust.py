#!/usr/bin/env python
"""Machine-checkable data-trust assertions for cn_data.

Exit codes:
  0 = trusted / pass
  2 = untrusted (trading must stay blocked)
  3 = environment / path error

Usage:
  python scripts/assert_data_trust.py
  python scripts/assert_data_trust.py --full-sample
  python scripts/assert_data_trust.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="", help="Override cn_data path")
    parser.add_argument("--sample", type=int, default=400)
    parser.add_argument("--full-sample", action="store_true", help="Sample up to 5000 stocks")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    from core import data_trust

    data_dir = Path(args.data_dir).expanduser() if args.data_dir else data_trust.CN_DATA_DIR
    if not data_dir.exists():
        print(f"ERROR: data dir missing: {data_dir}")
        return 3

    max_sample = 5000 if args.full_sample else args.sample
    report = data_trust.evaluate_data_trust(
        data_dir=data_dir,
        max_sample=max_sample,
        use_cache=not args.no_cache,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"trusted={report['trusted']} status={report['status']}")
        print(f"message={report['message']}")
        metrics = report.get("metrics") or {}
        print(
            "metrics:",
            f"severe_splice={metrics.get('severe_splice_ratio')}",
            f"tail_placeholder={metrics.get('tail_placeholder_ratio')}",
            f"sample={report.get('sample_size')}",
        )
        if report.get("reasons"):
            print("reasons:", "; ".join(report["reasons"]))
        if report.get("examples"):
            print("examples:")
            for ex in report["examples"][:5]:
                print(
                    f"  {ex.get('code')} {ex.get('last_date')} "
                    f"{ex.get('prev_close')}->{ex.get('last_close')} "
                    f"chg={ex.get('change_pct')}"
                )
        if not report["trusted"]:
            print("repair_hints:")
            for hint in report.get("repair_hints") or []:
                print(" ", hint)

    return 0 if report.get("trusted") else 2


if __name__ == "__main__":
    raise SystemExit(main())
