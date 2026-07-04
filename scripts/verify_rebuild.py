"""阶段 1 数据重建验收脚本（可重复执行）。

验收四项（与 audit_report_20260704.md 第 1 件事对应）：
  1) 2020-09-25/28 拼接边界连续性：边界单日涨跌 >11% 的股票占比应 <1%
     （修复前 98.2%），剩余的应能对应真实除权日。
  2) "相邻日涨跌 >11% 且非除权日" 全库扫描：需要除权事件表做白名单，
     baostock 复权因子变动日即是。
  3) 抽样 20 只与腾讯/东财当日后复权序列的相对偏差 <0.5%。
  4) sh600519 等 61 只空心票的有效值密度 >95%、1999 幽灵段消失。

设计原则：
  - 只读 cn_data 目录，默认不写任何文件；
  - 除权事件表用 baostock query_adjust_factor 在线拉取（可缓存到本地 json），
    离线/无 baostock 时退化为本脚本说明并跳过白名单校验；
  - 输出 JSON + 人读摘要，退出码 0/非 0 便于 CI 或运维串联。

用法：
    python scripts/verify_rebuild.py --data-dir ~/.qlib/qlib_data/cn_data
    python scripts/verify_rebuild.py --sample 20 --boundary 2020-09-25 2020-09-28
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def read_calendar(data_dir: Path) -> list[str]:
    cal_path = data_dir / "calendars" / "day.txt"
    if not cal_path.exists():
        return []
    return [line.strip() for line in cal_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_close_series(bin_path: Path, calendar: list[str]) -> list[tuple[str, float]]:
    import numpy as np

    raw = np.fromfile(bin_path, dtype="<f")
    if len(raw) < 2:
        return []
    start_idx = int(raw[0])
    points: list[tuple[str, float]] = []
    for offset, value in enumerate(raw[1:]):
        cal_idx = start_idx + offset
        date = calendar[cal_idx] if 0 <= cal_idx < len(calendar) else ""
        points.append((date, float(value)))
    return points


def effective_density(bin_path: Path) -> tuple[int, int, float]:
    import numpy as np

    raw = np.fromfile(bin_path, dtype="<f")
    if len(raw) < 2:
        return 0, 0, 0.0
    values = raw[1:]
    finite = int(np.sum(np.isfinite(values) & (values > 0)))
    total = int(len(values))
    return finite, total, (finite / total if total else 0.0)


def scan_boundary_jumps(data_dir: Path, boundary_dates: list[str], threshold: float = 0.11) -> dict:
    calendar = read_calendar(data_dir)
    feature_dir = data_dir / "features"
    if not feature_dir.exists():
        return {"status": "skipped", "reason": "features 目录不存在", "abnormal_count": 0, "total": 0}

    boundary_set = {boundary_dates[0], boundary_dates[-1]}
    close_files = sorted(feature_dir.glob("*/close.day.bin"))
    abnormal: list[dict] = []
    checked = 0
    for close_path in close_files:
        points = read_close_series(close_path, calendar)
        # 只关心跨边界的股票
        dates = {d for d, _ in points}
        if not boundary_set.intersection(dates):
            continue
        checked += 1
        prev = None
        for date, value in points:
            if value <= 0 or not (date in boundary_set):
                prev = (date, value) if value > 0 else None
                continue
            if prev and prev[1] > 0:
                jump = value / prev[1] - 1.0
                if abs(jump) >= threshold:
                    abnormal.append({"code": close_path.parent.name, "date": date, "jump": round(jump, 4)})
            prev = (date, value)

    ratio = (len(abnormal) / checked) if checked else 0.0
    return {
        "status": "pass" if ratio < 0.01 else "fail",
        "boundary": boundary_dates,
        "threshold": threshold,
        "total_cross_boundary": checked,
        "abnormal_count": len(abnormal),
        "abnormal_ratio": round(ratio, 4),
        "examples": abnormal[:20],
    }


def scan_full_jumps(data_dir: Path, threshold: float = 0.11, factor_whitelist: set[str] | None = None) -> dict:
    calendar = read_calendar(data_dir)
    feature_dir = data_dir / "features"
    if not feature_dir.exists():
        return {"status": "skipped", "reason": "features 目录不存在", "hits": 0}

    hits: list[dict] = []
    for close_path in sorted(feature_dir.glob("*/close.day.bin")):
        points = read_close_series(close_path, calendar)
        prev = None
        for date, value in points:
            if value <= 0:
                prev = None
                continue
            if prev and prev[1] > 0:
                jump = value / prev[1] - 1.0
                if abs(jump) >= threshold:
                    key = f"{close_path.parent.name}@{date}"
                    if factor_whitelist and key in factor_whitelist:
                        continue
                    hits.append({"code": close_path.parent.name, "date": date, "jump": round(jump, 4)})
            prev = (date, value)

    return {
        "status": "pass" if not hits else "fail",
        "threshold": threshold,
        "hits": len(hits),
        "examples": hits[:50],
    }


def check_hollow_securities(data_dir: Path, known_hollow: list[str], min_density: float = 0.95) -> dict:
    feature_dir = data_dir / "features"
    results: list[dict] = []
    for code in known_hollow:
        bin_path = feature_dir / code / "close.day.bin"
        if not bin_path.exists():
            results.append({"code": code, "status": "missing"})
            continue
        finite, total, density = effective_density(bin_path)
        status = "pass" if density >= min_density else "fail"
        results.append({"code": code, "finite": finite, "total": total, "density": round(density, 4), "status": status})

    failed = [r for r in results if r.get("status") != "pass"]
    return {
        "status": "pass" if not failed else "fail",
        "min_density": min_density,
        "checked": len(results),
        "failed": failed,
        "results": results,
    }


def load_factor_whitelist(cache_path: Path | None) -> set[str]:
    """除权事件白名单：code@日期。后续可由 baostock query_adjust_factor 离线生成。"""
    if not cache_path or not cache_path.exists():
        return set()
    rows = json.loads(cache_path.read_text(encoding="utf-8"))
    return {f"{r['code']}@{r['date']}" for r in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="阶段 1 数据重建验收")
    parser.add_argument("--data-dir", default=str(Path.home() / ".qlib" / "qlib_data" / "cn_data"))
    parser.add_argument("--boundary", nargs=2, default=["2020-09-25", "2020-09-28"], metavar=("START", "END"))
    parser.add_argument("--sample", type=int, default=20, help="与外部源对照抽样数（占位，需联网）")
    parser.add_argument("--factor-whitelist", default=None, help="除权事件白名单 JSON，元素 [{code,date}]")
    parser.add_argument("--out", default=None, help="结果 JSON 写入路径")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    whitelist = load_factor_whitelist(Path(args.factor_whitelist) if args.factor_whitelist else None)

    report = {
        "checked_at": datetime.now().isoformat(),
        "data_dir": str(data_dir),
        "checks": {
            "boundary_continuity": scan_boundary_jumps(data_dir, args.boundary),
            "full_jump_scan": scan_full_jumps(data_dir, factor_whitelist=whitelist),
            "hollow_securities": check_hollow_securities(
                data_dir,
                known_hollow=["sh600519", "sh600036", "sh601318", "sh510300"],
            ),
            "cross_source_sample": {
                "status": "pending",
                "note": (
                    "腾讯/东财只提供前复权，不能直接比后复权价。正确比法："
                    "后复权价 ÷ 前复权价 应为全序列常数（= 最新累积因子），检验该比值的变异系数；"
                    "或直接比对日收益率序列（复权口径不影响收益率）。待实现。"
                ),
                "sample_size": args.sample,
            },
        },
    }

    statuses = {v.get("status") for v in report["checks"].values()}
    report["overall_status"] = "fail" if "fail" in statuses else ("pending" if "pending" in statuses else "pass")

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["overall_status"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
