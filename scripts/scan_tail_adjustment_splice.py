#!/usr/bin/env python
"""Scan cn_data for tail adjustment-splice pollution.

Detects stocks where the latest bars have factor~1.0 while earlier bars carry a
real cumulative back-adjust factor, optionally with a large price jump.

Usage:
  python scripts/scan_tail_adjustment_splice.py
  python scripts/scan_tail_adjustment_splice.py --out ~/.qlib/cache/tail_splice_codes.txt
  python scripts/scan_tail_adjustment_splice.py --full --json-out report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))


def _read_calendar(data_dir: Path) -> list[str]:
    path = data_dir / "calendars" / "day.txt"
    return [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _is_a_share(code: str) -> bool:
    c = code.lower()
    return c.startswith(("sh6", "sz0", "sz3", "bj4", "bj8", "bj920"))


def scan(data_dir: Path, jump_threshold: float = 0.20) -> dict:
    calendar = _read_calendar(data_dir)
    feature_root = data_dir / "features"
    polluted: list[dict] = []
    placeholder_only: list[dict] = []
    total = 0

    for stock_dir in sorted(feature_root.iterdir()):
        if not stock_dir.is_dir() or not _is_a_share(stock_dir.name):
            continue
        close_path = stock_dir / "close.day.bin"
        factor_path = stock_dir / "factor.day.bin"
        if not close_path.exists() or not factor_path.exists():
            continue

        close_raw = np.fromfile(close_path, dtype="<f")
        factor_raw = np.fromfile(factor_path, dtype="<f")
        if len(close_raw) < 3 or len(factor_raw) < 3:
            continue
        start = int(close_raw[0])
        closes = close_raw[1:]
        factors = factor_raw[1:]
        valid = np.where(np.isfinite(closes) & (closes > 0))[0]
        if len(valid) < 2:
            continue
        total += 1
        i1 = int(valid[-1])
        i0 = int(valid[-2])
        f0 = float(factors[i0]) if i0 < len(factors) and np.isfinite(factors[i0]) else None
        f1 = float(factors[i1]) if i1 < len(factors) and np.isfinite(factors[i1]) else None
        hist_max = float(np.nanmax(factors[np.isfinite(factors)])) if np.isfinite(factors).any() else 1.0
        c0 = float(closes[i0])
        c1 = float(closes[i1])
        chg = c1 / c0 - 1.0 if c0 > 0 else 0.0
        d1 = calendar[start + i1] if 0 <= start + i1 < len(calendar) else ""

        tail_placeholder = hist_max > 1.01 and f1 is not None and f1 <= 1.01
        severe = (
            f0 is not None
            and f1 is not None
            and f0 >= 1.5
            and f1 <= 1.01
            and abs(chg) >= jump_threshold
        )
        row = {
            "code": stock_dir.name,
            "last_date": d1,
            "prev_close": round(c0, 4),
            "last_close": round(c1, 4),
            "change_pct": round(chg, 4),
            "prev_factor": f0,
            "last_factor": f1,
            "hist_max_factor": round(hist_max, 6),
            "severe_splice": severe,
            "tail_placeholder": tail_placeholder,
        }
        if severe:
            polluted.append(row)
        elif tail_placeholder:
            placeholder_only.append(row)

    return {
        "data_dir": str(data_dir),
        "total_scanned": total,
        "severe_splice_count": len(polluted),
        "severe_splice_ratio": round(len(polluted) / total, 4) if total else 0,
        "tail_placeholder_only_count": len(placeholder_only),
        "tail_placeholder_only_ratio": round(len(placeholder_only) / total, 4) if total else 0,
        "severe_examples": polluted[:20],
        "codes_severe": [r["code"] for r in polluted],
        "codes_placeholder": [r["code"] for r in placeholder_only],
        "codes_all_repair": sorted({r["code"] for r in polluted + placeholder_only}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan tail adjustment splice pollution")
    parser.add_argument(
        "--data-dir",
        default=str(Path.home() / ".qlib" / "qlib_data" / "cn_data"),
    )
    parser.add_argument("--out", default="", help="Write repair code list (one per line)")
    parser.add_argument("--json-out", default="", help="Write full JSON report")
    parser.add_argument("--jump-threshold", type=float, default=0.20)
    parser.add_argument(
        "--include-placeholder",
        action="store_true",
        help="Include non-jump placeholder-factor tails in --out list (recommended)",
    )
    args = parser.parse_args()

    report = scan(Path(args.data_dir).expanduser(), jump_threshold=args.jump_threshold)
    print(
        f"scanned={report['total_scanned']} "
        f"severe={report['severe_splice_count']} ({report['severe_splice_ratio']:.2%}) "
        f"placeholder_only={report['tail_placeholder_only_count']} "
        f"({report['tail_placeholder_only_ratio']:.2%})"
    )
    if report["severe_examples"]:
        print("examples:")
        for row in report["severe_examples"][:8]:
            print(
                f"  {row['code']} {row['last_date']} "
                f"{row['prev_close']}->{row['last_close']} ({row['change_pct']:+.1%}) "
                f"factor {row['prev_factor']}->{row['last_factor']}"
            )

    codes = report["codes_all_repair"] if args.include_placeholder else report["codes_severe"]
    # Always prefer full repair set for operational safety when writing --out
    if args.out:
        out_path = Path(args.out).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if not args.include_placeholder:
            # default for repair: include both severe and placeholder
            codes = report["codes_all_repair"]
        out_path.write_text("\n".join(codes) + ("\n" if codes else ""), encoding="utf-8")
        print(f"wrote {len(codes)} codes -> {out_path}")

    if args.json_out:
        path = Path(args.json_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote json -> {path}")

    # Non-zero if severe pollution exceeds 2%
    if report["severe_splice_ratio"] > 0.02:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
