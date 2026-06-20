import json
import struct
from pathlib import Path


CODES = [
    "sz300024", "sz300033", "sz300058", "sz300059", "sz300070", "sz300072",
    "sz300085", "sz300122", "sz300133", "sz300136", "sz300142", "sz300144",
    "sz300146", "sz300168", "sz300182", "sz300251", "sz300296", "sz300315",
    "sz300347", "sz300408", "sz300413", "sz300498", "sz300601", "sz300628",
]


def latest_date_for_bin(path: Path, calendar: list[str]) -> tuple[str, str]:
    if not path.exists():
        return "MISSING", "missing_close"

    size = path.stat().st_size
    if size < 8 or size % 4 != 0:
        return "ERROR", "bad_size"

    with path.open("rb") as handle:
        start_idx = int(struct.unpack("<f", handle.read(4))[0])

    value_count = size // 4 - 1
    last_idx = start_idx + value_count - 1
    if last_idx < 0 or last_idx >= len(calendar):
        return "ERROR", f"idx_out_of_range:{last_idx}"

    return calendar[last_idx], ""


def main():
    root = Path("/root/.qlib/qlib_data/cn_data")
    calendar = [
        line.strip()
        for line in (root / "calendars" / "day.txt").read_text().splitlines()
        if line.strip()
    ]

    rows = []
    for code in CODES:
        latest, error = latest_date_for_bin(root / "features" / code / "close.day.bin", calendar)
        rows.append({"code": code, "latest": latest, "error": error})

    print(json.dumps({
        "calendar_last": calendar[-1] if calendar else "",
        "rows": rows,
        "not_latest": [row for row in rows if row["latest"] != "2026-06-18"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
