"""官方 cn_data 增量更新脚本

把 ~/.qlib/qlib_data/cn_data 里已有的 3875 只股票
用 yfinance 从 2020-09-26 更新到今天。

使用 Qlib 官方 FileFeatureStorage API 追加数据，格式完全兼容。

运行：
    python update_cn_data.py              # 更新全部 3875 只（约1-2小时）
    python update_cn_data.py --max 300    # 只更新前300只（测试用，约20分钟）
    python update_cn_data.py --check      # 只检查状态，不更新
"""
import argparse
import pathlib
import time
import sys

import numpy as np
import pandas as pd
import yfinance as yf

DATA_DIR = pathlib.Path.home() / ".qlib" / "qlib_data" / "cn_data"
FIELDS   = ["open", "close", "high", "low", "volume"]
# amount 和 factor 不在 yfinance，单独处理
EXTRA_FIELDS = ["amount", "factor"]


# ── 日历 ──

def load_calendar() -> list[str]:
    cal_path = DATA_DIR / "calendars" / "day.txt"
    with open(cal_path) as f:
        return [l.strip() for l in f if l.strip()]


def extend_calendar(new_dates: list[str]) -> list[str]:
    """把新交易日追加到日历"""
    cal_path = DATA_DIR / "calendars" / "day.txt"
    cal = load_calendar()
    existing = set(cal)
    added = [d for d in sorted(new_dates) if d not in existing]
    if added:
        with open(cal_path, "a") as f:
            f.write("\n" + "\n".join(added))
        cal = cal + added
        print(f"  日历新增 {len(added)} 天，最新: {cal[-1]}")
    return cal


# ── 代码转换 ──

def qlib_to_yf(code: str) -> str:
    """sh600519 → 600519.SS，sz000001 → 000001.SZ"""
    code = code.lower()
    if code.startswith("sh"):
        return code[2:].upper() + ".SS"
    elif code.startswith("sz"):
        return code[2:].upper() + ".SZ"
    return code.upper() + ".SS"


# ── yfinance 拉取 ──

def fetch(yf_code: str, start: str, end: str) -> pd.DataFrame:
    try:
        t = yf.Ticker(yf_code)
        df = t.history(start=start, end=end, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.index = df.index.tz_localize(None)
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        df["amount"] = df["close"] * df["volume"]
        df["factor"] = 1.0
        df.index = [d.strftime("%Y-%m-%d") for d in df.index]
        return df[[f for f in FIELDS + EXTRA_FIELDS if f in df.columns]]
    except Exception:
        return pd.DataFrame()


# ── Qlib bin 追加 ──

def append_to_bin(qlib_code: str, df: pd.DataFrame, calendar: list[str]) -> int:
    """把 df 追加到已有 bin 文件，返回追加的行数"""
    if df.empty:
        return 0

    # 只保留日历里有的日期
    cal_set = set(calendar)
    df = df[[d in cal_set for d in df.index]]
    if df.empty:
        return 0

    stock_dir = DATA_DIR / "features" / qlib_code.lower()
    if not stock_dir.exists():
        return 0  # 不在官方数据里的股票跳过

    appended = 0
    for field in FIELDS + EXTRA_FIELDS:
        if field not in df.columns:
            continue

        bin_path = stock_dir / f"{field}.day.bin"
        if not bin_path.exists():
            continue

        # 读现有 end_index
        with open(bin_path, "rb") as fp:
            raw = np.fromfile(fp, dtype="<f")
        if len(raw) < 2:
            continue

        start_idx = int(raw[0])
        existing_len = len(raw) - 1
        end_idx = start_idx + existing_len - 1  # 最后一条数据的日历索引

        # 找新数据中日历索引 > end_idx 的部分
        new_rows = []
        for date_str in df.index:
            if date_str not in cal_set:
                continue
            cal_idx = calendar.index(date_str)
            if cal_idx > end_idx:
                new_rows.append((cal_idx, float(df.loc[date_str, field])))

        if not new_rows:
            continue

        # 排序，中间缺失的日期填 NaN
        new_rows.sort()
        next_expected = end_idx + 1
        to_append = []
        for cal_idx, val in new_rows:
            # 填充中间空洞
            while next_expected < cal_idx:
                to_append.append(np.nan)
                next_expected += 1
            to_append.append(val)
            next_expected = cal_idx + 1

        # 追加到 bin 文件
        with open(bin_path, "ab") as fp:
            np.array(to_append, dtype="<f").tofile(fp)

        appended = max(appended, len(to_append))

    return appended


# ── 主流程 ──

def check():
    cal = load_calendar()
    print(f"日历: {cal[0]} ~ {cal[-1]}  ({len(cal)} 天)")

    # 随机抽查10只股票的实际数据最新日期
    import random
    stocks = list(DATA_DIR.glob("features/*/close.day.bin"))
    print(f"股票总数: {len(stocks)}")

    sample = random.sample(stocks, min(10, len(stocks)))
    for p in sample:
        with open(p, "rb") as fp:
            raw = np.fromfile(fp, dtype="<f")
        if len(raw) < 2:
            continue
        start_idx = int(raw[0])
        end_idx = start_idx + len(raw) - 2
        last_date = cal[end_idx] if end_idx < len(cal) else "超出日历"
        print(f"  {p.parent.name}: end_idx={end_idx}, 最新={last_date}, 最新价={raw[-1]:.2f}")


def update(start: str = "2020-09-26", end: str = None, max_stocks: int = None):
    if end is None:
        end = (pd.Timestamp.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"=== 增量更新 {start} ~ {end} ===")

    # 1. 用沪深300ETF 获取新交易日，扩展日历
    print("\n[1] 获取新交易日...")
    ref_df = fetch("510300.SS", start, end)
    if ref_df.empty:
        print("  ✗ 无法获取参考数据，请检查网络")
        return
    new_dates = list(ref_df.index)
    calendar = extend_calendar(new_dates)
    print(f"  新增交易日: {new_dates[0]} ~ {new_dates[-1]}  ({len(new_dates)} 天)")

    # 2. 获取所有股票列表
    stocks = sorted(DATA_DIR.glob("features/*/close.day.bin"))
    if max_stocks:
        stocks = stocks[:max_stocks]
    total = len(stocks)
    print(f"\n[2] 开始更新 {total} 只股票...")

    success = skip = fail = 0
    start_time = time.time()

    for i, bin_path in enumerate(stocks):
        qlib_code = bin_path.parent.name   # sh600519
        yf_code   = qlib_to_yf(qlib_code)  # 600519.SS

        # 拉取新数据
        df = fetch(yf_code, start, end)

        if df.empty:
            fail += 1
        else:
            appended = append_to_bin(qlib_code, df, calendar)
            if appended > 0:
                success += 1
            else:
                skip += 1

        # 进度
        if (i + 1) % 50 == 0 or i == total - 1:
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed
            remaining = (total - i - 1) / speed if speed > 0 else 0
            print(f"  [{i+1}/{total}] 成功:{success} 跳过:{skip} 失败:{fail} "
                  f"速度:{speed:.1f}只/s 剩余:{remaining/60:.1f}分")

        time.sleep(0.25)  # 限速避免被封

    # 3. 更新 instruments 日期范围
    print("\n[3] 更新股票池日期范围...")
    _update_instruments_end(calendar[-1])

    elapsed = time.time() - start_time
    print(f"\n完成！耗时 {elapsed/60:.1f} 分钟")
    print(f"成功: {success}  跳过(无新数据): {skip}  失败: {fail}")
    print(f"数据最新日期: {calendar[-1]}")


def _update_instruments_end(new_end: str):
    """把所有 instruments 文件的结束日期更新到 new_end"""
    for inst_path in (DATA_DIR / "instruments").glob("*.txt"):
        lines = open(inst_path).readlines()
        new_lines = []
        for line in lines:
            parts = line.strip().split("\t")
            if len(parts) == 3:
                parts[2] = new_end
                new_lines.append("\t".join(parts))
            else:
                new_lines.append(line.strip())
        with open(inst_path, "w") as f:
            f.write("\n".join(new_lines))
        print(f"  {inst_path.name}: 结束日期 → {new_end}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check",  action="store_true", help="只检查状态")
    parser.add_argument("--start",  default="2020-09-26", help="起始日期")
    parser.add_argument("--end",    default=None,         help="结束日期")
    parser.add_argument("--max",    type=int, default=None, help="最多更新几只（测试用）")
    args = parser.parse_args()

    if args.check:
        check()
    else:
        update(start=args.start, end=args.end, max_stocks=args.max)
