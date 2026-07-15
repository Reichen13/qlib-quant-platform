"""Trim trailing NaN/zero garbage from delisted (or long-halted) Qlib feature bins.

For each code in a codes file, find the last valid close, then truncate all
feature *.day.bin under that stock to the same length. Optionally rewrite
instruments/*.txt end dates for those codes.

Usage:
  python scripts/trim_delisted_nan_tails.py --codes-file ~/.qlib/cache/lagging_0703.txt
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

DATA_DIR = Path.home() / ".qlib" / "qlib_data" / "cn_data"


def load_calendar() -> list[str]:
    return [
        line.strip()
        for line in (DATA_DIR / "calendars" / "day.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def last_valid_close_offset(close_path: Path) -> tuple[int, int, float] | None:
    """Return (start_idx, last_valid_offset, last_valid_value) or None."""
    raw = np.fromfile(close_path, dtype="<f")
    if len(raw) < 2:
        return None
    start_idx = int(raw[0])
    vals = raw[1:]
    valid = np.where(np.isfinite(vals) & (vals > 0))[0]
    if len(valid) == 0:
        return None
    off = int(valid[-1])
    return start_idx, off, float(vals[off])


def truncate_stock_bins(code: str, keep_len: int, start_idx: int) -> int:
    """Truncate all day.bin under features/<code> to keep_len values (plus start idx)."""
    stock_dir = DATA_DIR / "features" / code.lower()
    if not stock_dir.is_dir():
        return 0
    n = 0
    for bin_path in stock_dir.glob("*.day.bin"):
        raw = np.fromfile(bin_path, dtype="<f")
        if len(raw) < 2:
            continue
        # Prefer existing start_idx if present; force consistency with close
        values = raw[1 : 1 + keep_len]
        if len(values) < keep_len:
            # shorter than close — leave as-is
            continue
        out = np.empty(keep_len + 1, dtype="<f")
        out[0] = float(start_idx)
        out[1:] = values
        out.tofile(bin_path)
        n += 1
    return n


def patch_instruments_end(code_end: dict[str, str]) -> None:
    inst_dir = DATA_DIR / "instruments"
    if not inst_dir.is_dir():
        return
    for path in inst_dir.glob("*.txt"):
        lines_out = []
        changed = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split("\t")
            if len(parts) == 3:
                key = parts[0].strip()
                # instruments may be SH600000 or sh600000
                low = key.lower()
                if low in code_end:
                    parts[2] = code_end[low]
                    changed += 1
                elif key.upper() in {c.upper() for c in code_end}:
                    # match ignoring case
                    for c, end in code_end.items():
                        if c.upper() == key.upper():
                            parts[2] = end
                            changed += 1
                            break
                lines_out.append("\t".join(parts))
            elif line.strip():
                lines_out.append(line.strip())
        if changed:
            path.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
            print(f"  instruments {path.name}: patched {changed} rows")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes-file", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    codes = [
        line.strip().lower()
        for line in Path(args.codes_file).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    cal = load_calendar()
    print(f"trim delisted tails: {len(codes)} codes, dry_run={args.dry_run}")

    code_end: dict[str, str] = {}
    trimmed = skipped = 0
    for code in codes:
        close_path = DATA_DIR / "features" / code / "close.day.bin"
        if not close_path.exists():
            skipped += 1
            continue
        info = last_valid_close_offset(close_path)
        if info is None:
            print(f"  SKIP {code}: no valid close")
            skipped += 1
            continue
        start_idx, last_off, last_val = info
        keep_len = last_off + 1
        end_cal_idx = start_idx + last_off
        end_date = cal[end_cal_idx] if 0 <= end_cal_idx < len(cal) else ""
        raw = np.fromfile(close_path, dtype="<f")
        tail = len(raw) - 1 - last_off
        if tail <= 0:
            skipped += 1
            continue
        print(
            f"  {code}: last_valid={end_date} val={last_val:.4f} "
            f"trim_tail={tail} keep_len={keep_len}"
        )
        if not args.dry_run:
            n = truncate_stock_bins(code, keep_len, start_idx)
            print(f"    truncated {n} bins")
            if end_date:
                code_end[code] = end_date
            trimmed += 1
        else:
            trimmed += 1

    if not args.dry_run and code_end:
        patch_instruments_end(code_end)

    print(f"done trimmed={trimmed} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
