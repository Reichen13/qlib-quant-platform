import argparse
import json
from collections import Counter
from pathlib import Path


STALE_CODES = {
    "sh600068", "sh600074", "sh600190", "sh600220", "sh600270", "sh600277",
    "sh600297", "sh600317", "sh600432", "sh600485", "sh600705", "sh600804",
    "sh600811", "sh600823", "sh600837", "sh600978", "sh601258", "sh601558",
    "sh601989", "sz000046", "sz000413", "sz000540", "sz000627", "sz000667",
    "sz000671", "sz000780", "sz000961", "sz002411", "sz002450", "sz300104",
    "sh600005", "sh600087", "sh600102", "sh600591", "sh600747", "sh600849",
    "sh601268",
}


def normalize_code(line: str) -> str:
    parts = line.strip().split("\t")
    return parts[0].lower() if parts and parts[0] else ""


def build_candidate(lines: list[str], *, remove_stale: bool, dedupe: bool) -> tuple[list[str], list[dict]]:
    output = []
    seen = set()
    removed = []

    for index, line in enumerate(lines, start=1):
        code = normalize_code(line)
        if not code:
            continue

        if remove_stale and code in STALE_CODES:
            removed.append({"line": index, "code": code, "reason": "stale_or_delisted", "raw": line})
            continue

        if dedupe and code in seen:
            removed.append({"line": index, "code": code, "reason": "duplicate", "raw": line})
            continue

        seen.add(code)
        output.append(line)

    return output, removed


def main():
    parser = argparse.ArgumentParser(description="Generate a candidate cleaned csi300 instrument file.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--remove-stale", action="store_true")
    parser.add_argument("--dedupe", action="store_true")
    args = parser.parse_args()

    lines = [line for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    before_codes = [normalize_code(line) for line in lines if normalize_code(line)]
    candidate, removed = build_candidate(lines, remove_stale=args.remove_stale, dedupe=args.dedupe)
    after_codes = [normalize_code(line) for line in candidate if normalize_code(line)]

    args.output.write_text("\n".join(candidate) + "\n", encoding="utf-8")
    args.report.write_text(json.dumps({
        "input": str(args.input),
        "output": str(args.output),
        "remove_stale": args.remove_stale,
        "dedupe": args.dedupe,
        "before_raw_rows": len(lines),
        "before_unique_codes": len(set(before_codes)),
        "before_duplicate_count": len(before_codes) - len(set(before_codes)),
        "after_raw_rows": len(candidate),
        "after_unique_codes": len(set(after_codes)),
        "after_duplicate_count": len(after_codes) - len(set(after_codes)),
        "removed_count": len(removed),
        "removed_reason_counts": Counter(item["reason"] for item in removed),
        "removed": removed,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
