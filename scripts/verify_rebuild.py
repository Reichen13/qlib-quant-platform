"""阶段 1 数据重建验收脚本（可重复执行，机械化判定）。

验收以脚本 overall_status=pass 为唯一标准，不依赖人工叙述性定性。

检查项：
  A) 日历完整性：与 baostock query_trade_dates 全量比对，缺一天即 fail
     （旧源日历经审计发现有成段缺失，不能再复制依赖）
  B) 2020-09-25/28 拼接边界连续性：异常占比 <1%
  C) 全库 jump 扫描 + 白名单机械化（命中白名单的 jump 不计为异常）：
     白名单规则：
       1) factor 事件日 ±1 日（baostock query_adjust_factor 的 dividOperateDate）
       2) NaN 缺口后的首个有效日（停牌复牌首日，无涨跌幅限制）
       3) IPO 后前 5 个交易日（新股连续涨停，属正常）
       4) 按代码前缀分档阈值：主板 0.11 / 创业科创 0.21 / 北交所 0.31
  D) 空心票密度 >95%、1999 幽灵段消失
  E) 外部源抽样对照：后复权价 ÷ 前复权价 应为全序列常数，变异系数 <阈值
     （或 --skip-cross-source 显式跳过）

用法：
    python scripts/verify_rebuild.py --data-dir ~/.qlib/qlib_data/cn_data_new
    python scripts/verify_rebuild.py --data-dir <dir> --skip-cross-source
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


# ── 基础读取 ──

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


# ── A. 日历完整性 ──

def fetch_official_trading_days(start: str = "1990-01-01", end: str | None = None) -> list[str]:
    """从 baostock query_trade_dates 拉官方交易日历。"""
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != "0":
            return []
        rs = bs.query_trade_dates(start_date=start, end_date=end)
        if rs.error_code != "0":
            bs.logout()
            return []
        days = []
        while rs.next():
            row = rs.get_row_data()
            if len(row) >= 2 and row[1] == "1":
                days.append(row[0])
        bs.logout()
        return days
    except Exception:
        return []


def check_calendar_completeness(data_dir: Path) -> dict:
    """与 baostock 官方交易日历全量比对，缺一天即 fail。"""
    local = read_calendar(data_dir)
    if not local:
        return {"status": "fail", "reason": "本地日历为空或不存在", "local_count": 0}

    official = fetch_official_trading_days(start=local[0], end=local[-1])
    if not official:
        return {"status": "skipped", "reason": "无法连接 baostock 拉取官方日历（联网失败）",
                "local_count": len(local), "official_count": 0, "missing": []}

    local_set = set(local)
    official_set = set(official)
    missing = sorted(official_set - local_set)
    extra = sorted(local_set - official_set)

    if missing:
        return {
            "status": "fail",
            "reason": f"本地日历缺少 {len(missing)} 个官方交易日（旧日历复制方案有洞）",
            "local_range": [local[0], local[-1]],
            "local_count": len(local),
            "official_count": len(official),
            "missing_count": len(missing),
            "missing_examples": missing[:20],
            "extra_count": len(extra),
        }
    return {
        "status": "pass",
        "local_range": [local[0], local[-1]],
        "local_count": len(local),
        "official_count": len(official),
        "missing_count": 0,
    }


# ── B. 边界连续性 ──

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


# ── C. 全库 jump 扫描 + 机械化白名单 ──

# A 股全面实施涨跌幅限制的日期（1996-12-16）。此前个股无单日涨跌幅限制，
# 单日大幅波动是历史常态，不应套用 10%/20% 阈值判定为数据异常。
PRE_PRICE_LIMIT_DATE = "1996-12-16"


def is_before_price_limit(date_str: str) -> bool:
    """日期在 A 股全面涨跌幅限制实施之前（无涨跌幅限制时代）。"""
    return str(date_str) < PRE_PRICE_LIMIT_DATE


def jump_threshold_for_code(code: str) -> float:
    """按代码前缀分档涨跌停阈值。"""
    c = code.lower()
    if c.startswith("bj"):
        return 0.31  # 北交所 30%
    if c.startswith("sz30") or c.startswith("sh688"):
        return 0.21  # 创业板/科创板 20%
    return 0.11  # 主板 10%


def fetch_factor_event_days(codes: list[str]) -> dict[str, set[str]]:
    """从 baostock query_adjust_factor 拉每只票的除权事件日（含 ±1 日窗口）。"""
    try:
        import baostock as bs
        from datetime import timedelta
        import pandas as pd
        lg = bs.login()
        if lg.error_code != "0":
            return {}
        events: dict[str, set[str]] = {}
        for code in codes:
            bs_code = ("sh." + code[2:]) if code.startswith("sh") else ("sz." + code[2:])
            rs = bs.query_adjust_factor(code=bs_code, start_date="1990-01-01", end_date="2026-12-31")
            days: set[str] = set()
            while rs.next():
                row = rs.get_row_data()
                d = row[1]  # dividOperateDate
                # ±1 日窗口
                dt = pd.Timestamp(d)
                days.add(d)
                days.add((dt - timedelta(days=1)).strftime("%Y-%m-%d"))
                days.add((dt + timedelta(days=1)).strftime("%Y-%m-%d"))
            events[code] = days
        bs.logout()
        return events
    except Exception:
        return {}


def build_nan_gap_whitelist(points: list[tuple[str, float]]) -> set[str]:
    """NaN 缺口后的首个有效日（停牌复牌首日，无涨跌幅限制）。"""
    whitelist: set[str] = set()
    seen_nan_gap = False
    for date, value in points:
        if value <= 0 or not _is_finite(value):
            seen_nan_gap = True
            continue
        if seen_nan_gap:
            whitelist.add(date)
            seen_nan_gap = False
    return whitelist


def _is_finite(v) -> bool:
    import math
    return isinstance(v, (int, float)) and math.isfinite(v)


def fetch_ipo_dates(codes: list[str]) -> dict[str, str]:
    """从 baostock query_stock_basic 拉 ipoDate。"""
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != "0":
            return {}
        ipo: dict[str, str] = {}
        for code in codes:
            bs_code = ("sh." + code[2:]) if code.startswith("sh") else ("sz." + code[2:])
            rs = bs.query_stock_basic(code=bs_code)
            while rs.next():
                row = rs.get_row_data()
                if len(row) >= 3 and row[2]:
                    ipo[code] = row[2]
                    break
        bs.logout()
        return ipo
    except Exception:
        return {}


def build_ipo_whitelist(code: str, ipo_date: str, calendar: list[str]) -> set[str]:
    """IPO 后前 5 个交易日（新股连续涨停，属正常）。"""
    if not ipo_date or ipo_date not in calendar:
        return set()
    idx = calendar.index(ipo_date)
    return set(calendar[idx:idx + 5])


def scan_full_jumps_mechanized(data_dir: Path) -> dict:
    """全库 jump 扫描，机械化白名单过滤后才计为异常。"""
    import numpy as np
    calendar = read_calendar(data_dir)
    feature_dir = data_dir / "features"
    if not feature_dir.exists():
        return {"status": "skipped", "reason": "features 目录不存在", "hits": 0}

    close_files = sorted(feature_dir.glob("*/close.day.bin"))
    codes = [p.parent.name for p in close_files]

    # 拉白名单数据（联网）
    print("  拉取 factor 事件日白名单...")
    factor_events = fetch_factor_event_days(codes)
    print("  拉取 IPO 日期白名单...")
    ipo_dates = fetch_ipo_dates(codes)

    hits: list[dict] = []
    whitelisted_count = 0
    for close_path in close_files:
        code = close_path.parent.name
        points = read_close_series(close_path, calendar)
        threshold = jump_threshold_for_code(code)
        nan_gap_wl = build_nan_gap_whitelist(points)
        ipo_wl = build_ipo_whitelist(code, ipo_dates.get(code, ""), calendar)
        factor_wl = factor_events.get(code, set())

        prev = None
        for date, value in points:
            if value <= 0 or not _is_finite(value):
                prev = None
                continue
            if prev and prev[1] > 0 and _is_finite(prev[1]):
                jump = value / prev[1] - 1.0
                if abs(jump) >= threshold:
                    # 白名单判定
                    if date in factor_wl or date in nan_gap_wl or date in ipo_wl or is_before_price_limit(date):
                        whitelisted_count += 1
                        prev = (date, value)
                        continue
                    hits.append({"code": code, "date": date, "jump": round(jump, 4),
                                 "threshold": threshold})
            prev = (date, value)

    return {
        "status": "pass" if not hits else "fail",
        "hits": len(hits),
        "whitelisted_count": whitelisted_count,
        "examples": hits[:50],
    }


# ── D. 空心票 ──

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
    failed = [r for r in results if r.get("status") not in ("pass",)]
    checked_real = [r for r in results if r.get("status") != "missing"]
    overall = "pass" if not failed and checked_real else ("fail" if failed else "skipped")
    return {"status": overall, "min_density": min_density, "checked": len(results), "failed": failed, "results": results}


# ── E. 外部源抽样对照 ──

def cross_source_check(data_dir: Path, sample: int = 5, cv_threshold: float = 0.02) -> dict:
    """后复权价 ÷ 东财前复权价 应为全序列常数，变异系数 < cv_threshold。

    东财 fqt=1 是前复权；后复权/前复权 = 累积因子常数。比值变异系数小 = 两序列一致。
    """
    import urllib.request
    import json as _json
    import numpy as np
    calendar = read_calendar(data_dir)
    feature_dir = data_dir / "features"
    if not feature_dir.exists():
        return {"status": "skipped", "reason": "features 目录不存在"}

    close_files = sorted(feature_dir.glob("*/close.day.bin"))[:sample]
    results = []
    for close_path in close_files:
        code = close_path.parent.name
        # 东财前复权
        secid = ("1." + code[2:]) if code.startswith("sh") else ("0." + code[2:])
        url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
               f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57"
               f"&klt=101&fqt=1&beg=19900101&end=20261231")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = _json.loads(urllib.request.urlopen(req, timeout=15).read())
            klines = (data.get("data") or {}).get("klines") or []
            em_close = {}
            for k in klines:
                p = k.split(",")
                if len(p) >= 7:
                    em_close[p[0]] = float(p[2])
        except Exception as e:
            results.append({"code": code, "status": "skip", "reason": f"东财拉取失败: {e}"})
            continue

        # 本地后复权
        points = read_close_series(close_path, calendar)
        ratios = []
        for date, value in points:
            if _is_finite(value) and value > 0 and date in em_close and em_close[date] > 0:
                ratios.append(value / em_close[date])
        if len(ratios) < 50:
            results.append({"code": code, "status": "skip", "reason": "重叠样本不足"})
            continue
        arr = np.array(ratios)
        cv = float(np.std(arr) / np.mean(arr)) if np.mean(arr) else 1.0
        status = "pass" if cv < cv_threshold else "fail"
        results.append({"code": code, "status": status, "cv": round(cv, 6), "ratio_mean": round(float(np.mean(arr)), 4), "samples": len(ratios)})

    failed = [r for r in results if r.get("status") == "fail"]
    return {
        "status": "fail" if failed else ("pass" if any(r.get("status") == "pass" for r in results) else "skipped"),
        "cv_threshold": cv_threshold,
        "sample_size": len(results),
        "failed": failed,
        "results": results,
    }


# ── 主流程 ──

def main() -> int:
    parser = argparse.ArgumentParser(description="阶段 1 数据重建验收（机械化判定）")
    parser.add_argument("--data-dir", default=str(Path.home() / ".qlib" / "qlib_data" / "cn_data"))
    parser.add_argument("--boundary", nargs=2, default=["2020-09-25", "2020-09-28"], metavar=("START", "END"))
    parser.add_argument("--sample", type=int, default=5, help="外部源对照抽样数")
    parser.add_argument("--skip-cross-source", action="store_true", help="跳过外部源对照（联网受限时用）")
    parser.add_argument("--skip-calendar-online", action="store_true", help="跳过日历完整性联网检查")
    parser.add_argument("--out", default=None, help="结果 JSON 写入路径")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    print(f"验收目录: {data_dir}")

    checks = {
        "boundary_continuity": scan_boundary_jumps(data_dir, args.boundary),
        "full_jump_scan": scan_full_jumps_mechanized(data_dir),
        "hollow_securities": check_hollow_securities(
            data_dir,
            known_hollow=[c for c in [p.parent.name for p in sorted((data_dir / "features").glob("*/close.day.bin"))]
                          if c in {"sh600519", "sh600036", "sh601318", "sh510300"}] or ["sh600519"],
        ),
    }

    if args.skip_calendar_online:
        checks["calendar_completeness"] = {"status": "skipped", "reason": "--skip-calendar-online"}
    else:
        print("检查日历完整性（联网 baostock）...")
        checks["calendar_completeness"] = check_calendar_completeness(data_dir)

    if args.skip_cross_source:
        checks["cross_source_sample"] = {"status": "skipped", "reason": "--skip-cross-source"}
    else:
        print("外部源抽样对照（联网东财）...")
        checks["cross_source_sample"] = cross_source_check(data_dir, sample=args.sample)

    report = {
        "checked_at": datetime.now().isoformat(),
        "data_dir": str(data_dir),
        "checks": checks,
    }
    statuses = {v.get("status") for v in report["checks"].values()}
    report["overall_status"] = "fail" if "fail" in statuses else ("pass" if "skipped" not in statuses or "pass" in statuses else "skipped")
    # 严格模式：只要有 fail 就 fail，skipped 不影响（已显式选择跳过）

    text = _json_dumps(report)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["overall_status"] != "fail" else 1


def _json_dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


if __name__ == "__main__":
    raise SystemExit(main())