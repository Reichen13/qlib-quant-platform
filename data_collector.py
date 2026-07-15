"""Qlib 数据更新器 v2：yfinance → Qlib bin 格式

数据源：yfinance（Yahoo Finance），在 WSL2 下可正常工作
支持：A股ETF、沪深300成分股、指数

运行：
    python data_collector.py --action check   # 检查状态
    python data_collector.py --action update  # 增量更新（推荐，约10分钟）
    python data_collector.py --action init    # 全量收集（约2-3小时）
"""
import os
import sys
import struct
import argparse
import time
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ── 配置 ──
QLIB_DATA_DIR = Path.home() / ".qlib" / "qlib_data" / "cn_data_akshare"

# 8 个行业 ETF（Yahoo Finance 代码）
SECTOR_ETFS = {
    "sh512880": "512880.SS",  # 证券ETF
    "sh512010": "512010.SS",  # 医药ETF
    "sh515030": "515030.SS",  # 新能源车
    "sh512660": "512660.SS",  # 军工ETF
    "sh512400": "512400.SS",  # 有色金属
    "sz159995": "159995.SZ",  # 芯片ETF
    "sh512200": "512200.SS",  # 房地产ETF
    "sh515880": "515880.SS",  # 通信ETF
}

# 宽基 ETF
BROAD_ETFS = {
    "sh510300": "510300.SS",  # 沪深300ETF
    "sh510500": "510500.SS",  # 中证500ETF
    "sz159915": "159915.SZ",  # 创业板ETF
    "sh510050": "510050.SS",  # 上证50ETF
}

# CSI300 部分成分股（Yahoo Finance 格式，精选流动性好的）
CSI300_SAMPLE = {
    "sh600519": "600519.SS",  # 贵州茅台
    "sh600036": "600036.SS",  # 招商银行
    "sh601318": "601318.SS",  # 中国平安
    "sh600276": "600276.SS",  # 恒瑞医药
    "sh300750": "300750.SZ",  # 宁德时代
    "sh601899": "601899.SS",  # 紫金矿业
    "sh000300": "000300.SS",  # 沪深300指数
}


# ── yfinance 数据拉取 ──

def fetch_yfinance(yf_code: str, start: str, end: str) -> pd.DataFrame:
    """用 yfinance 拉取数据"""
    import yfinance as yf
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
        df["factor"] = 1.0  # 已复权

        keep = ["open", "high", "low", "close", "volume", "amount", "factor"]
        df = df[[c for c in keep if c in df.columns]].astype(float)
        df = df[df["close"] > 0].dropna()
        return df
    except Exception as e:
        return pd.DataFrame()


# ── Qlib bin 格式写入 ──

def _get_trading_calendar(data_dir: Path) -> list:
    """读取交易日历，返回日期列表"""
    cal_path = data_dir / "calendars" / "day.txt"
    if not cal_path.exists():
        return []
    with open(cal_path) as f:
        return [line.strip() for line in f if line.strip()]


def _date_to_index(date: pd.Timestamp, calendar: list) -> int:
    """把日期转换为日历索引"""
    date_str = date.strftime("%Y-%m-%d")
    try:
        return calendar.index(date_str)
    except ValueError:
        # 找最近的日历日期
        for i, d in enumerate(calendar):
            if d >= date_str:
                return i
        return len(calendar) - 1


def write_bin(series: pd.Series, output_path: Path, calendar: list):
    """写入 Qlib bin 格式

    格式：前4字节为起始日历索引（uint32），之后是 float32 数组
    NaN 用 np.nan 填充（Qlib 会自动处理）
    """
    if series.empty:
        return

    # 找到第一个有效日期的日历索引
    start_idx = _date_to_index(series.index[0], calendar)

    values = series.values.astype(np.float32)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(struct.pack("<I", start_idx))
        f.write(values.tobytes())


def save_to_qlib(qlib_code: str, df: pd.DataFrame, data_dir: Path, calendar: list) -> bool:
    """把 DataFrame 存为 Qlib 二进制格式"""
    if df.empty:
        return False

    stock_dir = data_dir / "features" / qlib_code.lower()
    fields = ["open", "high", "low", "close", "volume", "amount", "factor"]

    for field in fields:
        if field not in df.columns:
            continue

        output_path = stock_dir / f"{field}.day.bin"

        # 如果已有旧数据，合并（增量更新）
        if output_path.exists():
            old_df = read_from_qlib(qlib_code, field, data_dir, calendar)
            if not old_df.empty:
                combined = pd.concat([old_df, df[[field]]])
                combined = combined[~combined.index.duplicated(keep="last")]
                combined = combined.sort_index()
                series = combined[field]
            else:
                series = df[field]
        else:
            series = df[field]

        write_bin(series, output_path, calendar)

    return True


def read_from_qlib(qlib_code: str, field: str, data_dir: Path, calendar: list) -> pd.DataFrame:
    """从 Qlib bin 格式读取（用于增量合并）"""
    bin_path = data_dir / "features" / qlib_code.lower() / f"{field}.day.bin"
    if not bin_path.exists():
        return pd.DataFrame()

    try:
        with open(bin_path, "rb") as f:
            start_idx = struct.unpack("<I", f.read(4))[0]
            values = np.frombuffer(f.read(), dtype=np.float32)

        if start_idx >= len(calendar) or len(values) == 0:
            return pd.DataFrame()

        end_idx = min(start_idx + len(values), len(calendar))
        dates = pd.to_datetime(calendar[start_idx:end_idx])
        series = pd.Series(values[:len(dates)], index=dates, name=field)
        return series.to_frame()
    except Exception:
        return pd.DataFrame()


# ── 日历和股票池管理 ──

def update_calendar(data_dir: Path, new_dates: set) -> list:
    """合并更新交易日历，返回完整日历"""
    cal_path = data_dir / "calendars" / "day.txt"
    cal_path.parent.mkdir(parents=True, exist_ok=True)

    # 读取现有日历
    existing = set()
    if cal_path.exists():
        with open(cal_path) as f:
            existing = {l.strip() for l in f if l.strip()}

    # 合并新日期
    new_strs = {d.strftime("%Y-%m-%d") if hasattr(d, 'strftime') else d
                for d in new_dates}
    merged = sorted(existing | new_strs)

    with open(cal_path, "w") as f:
        f.write("\n".join(merged))

    print(f"  日历更新: {len(merged)} 个交易日（最新: {merged[-1] if merged else '无'}）")
    return merged


def update_instruments(data_dir: Path, pool_name: str,
                       codes: list, start: str, end: str):
    """更新股票池文件"""
    inst_dir = data_dir / "instruments"
    inst_dir.mkdir(parents=True, exist_ok=True)

    lines = [f"{c.upper()}\t{start}\t{end}" for c in sorted(codes)]
    with open(inst_dir / f"{pool_name}.txt", "w") as f:
        f.write("\n".join(lines))
    print(f"  股票池 [{pool_name}]: {len(codes)} 只")


# ── 主流程 ──

def collect(
    target: dict,
    start: str,
    end: str,
    data_dir: Path,
    calendar: list,
) -> tuple[int, set]:
    """批量收集指定标的，返回（成功数, 新日期集合）"""
    success = 0
    all_dates = set()

    for qlib_code, yf_code in target.items():
        df = fetch_yfinance(yf_code, start, end)
        if df.empty:
            print(f"  ✗ {qlib_code} ({yf_code}): 无数据")
            continue

        all_dates.update(df.index.tolist())
        ok = save_to_qlib(qlib_code, df, data_dir, calendar)
        status = "✓" if ok else "✗"
        print(f"  {status} {qlib_code}: {len(df)} 条 "
              f"({df.index[0].date()} ~ {df.index[-1].date()})")
        if ok:
            success += 1
        time.sleep(0.5)

    return success, all_dates


def run_update(start: str = None, end: str = None, data_dir: Path = None):
    """增量更新：只拉最近数据"""
    if data_dir is None:
        data_dir = QLIB_DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    if end is None:
        end = (pd.Timestamp.now() + pd.Timedelta(days=1, unit="D")).strftime("%Y-%m-%d")
    if start is None:
        start = (pd.Timestamp.now() - pd.Timedelta(days=40, unit="D")).strftime("%Y-%m-%d")

    print(f"=== 增量更新 {start} ~ {end} ===\n")

    # 第一步：先拉沪深300ETF建立日历基准
    print("[0/3] 建立交易日历基准...")
    ref_df = fetch_yfinance("510300.SS", start, end)
    if not ref_df.empty:
        calendar = update_calendar(data_dir, set(ref_df.index.tolist()))
    else:
        calendar = _get_trading_calendar(data_dir)
    if not calendar:
        print("  ✗ 无法建立交易日历，请检查网络")
        return 0

    all_dates = set()

    print("[1/3] 宽基 ETF...")
    n1, d1 = collect(BROAD_ETFS, start, end, data_dir, calendar)
    all_dates |= d1

    print("\n[2/3] 行业 ETF...")
    n2, d2 = collect(SECTOR_ETFS, start, end, data_dir, calendar)
    all_dates |= d2

    print("\n[3/3] 部分个股 + 指数...")
    n3, d3 = collect(CSI300_SAMPLE, start, end, data_dir, calendar)
    all_dates |= d3

    # 更新日历和股票池
    print()
    if all_dates:
        calendar = update_calendar(data_dir, all_dates)

    end_date = pd.Timestamp.now().strftime("%Y-%m-%d")
    all_codes = list(BROAD_ETFS.keys()) + list(SECTOR_ETFS.keys())
    update_instruments(data_dir, "etf", all_codes, "2010-01-01", end_date)
    update_instruments(data_dir, "csi300_sample",
                       list(CSI300_SAMPLE.keys()), "2005-01-01", end_date)
    all_stock_codes = [
        f.parent.name.upper()
        for f in data_dir.glob("features/*/close.day.bin")
    ]
    update_instruments(data_dir, "all", all_stock_codes, "2005-01-01", end_date)

    total = n1 + n2 + n3
    total_target = len(BROAD_ETFS) + len(SECTOR_ETFS) + len(CSI300_SAMPLE)
    print(f"\n完成：{total}/{total_target} 只成功")
    print(f"数据目录：{data_dir}")

    # 验证 Qlib 能否读取
    print("\n=== 验证 Qlib 读取 ===")
    _verify_qlib(data_dir)

    return total


def run_init(start: str = "2015-01-01", end: str = None, data_dir: Path = None):
    """全量收集（历史数据）"""
    if end is None:
        end = (pd.Timestamp.now() + pd.Timedelta(days=1, unit="D")).strftime("%Y-%m-%d")
    print(f"=== 全量收集 {start} ~ {end} ===")
    print("提示：数据量大，ETF约 10 年历史，预计 5-10 分钟\n")
    run_update(start=start, end=end, data_dir=data_dir)


def _verify_qlib(data_dir: Path):
    """验证数据能被 Qlib 正确读取"""
    try:
        import qlib
        from qlib.config import REG_CN
        qlib.init(provider_uri=str(data_dir), region=REG_CN)

        from qlib.data import D
        # 用 ETF 代码测试
        test_codes = ["SH510300", "SH512880"]
        instrs = D.list_instruments(
            D.instruments("etf"),
            start_time="2024-01-01",
            end_time="2024-12-31",
            as_list=True,
        )
        print(f"  股票池 [etf]: {len(instrs)} 只")

        if instrs:
            df = D.features(
                instrs[:2],
                ["$close", "$volume"],
                start_time="2024-01-01",
                end_time="2024-06-30",
            )
            print(f"  数据读取: {df.shape[0]} 行")
            if not df.empty:
                print(f"  日期范围: {df.index.get_level_values('datetime').min().date()} "
                      f"~ {df.index.get_level_values('datetime').max().date()}")
                print("  ✅ Qlib 读取验证通过！")
                return True
        print("  ⚠️ 数据为空，请检查")
        return False
    except Exception as e:
        print(f"  ✗ Qlib 读取失败: {e}")
        return False


def check_status(data_dir: Path = None):
    """检查数据状态"""
    dirs = {
        "官方数据（Yahoo/2020前）": Path.home() / ".qlib" / "qlib_data" / "cn_data",
        "akshare数据（新）": QLIB_DATA_DIR if data_dir is None else data_dir,
    }

    print("=== 数据状态检查 ===\n")
    for label, d in dirs.items():
        print(f"[{label}]")
        if not d.exists():
            print("  ✗ 目录不存在\n")
            continue

        stocks = list(d.glob("features/*/close.day.bin"))
        cal = d / "calendars" / "day.txt"
        if cal.exists():
            lines = open(cal).readlines()
            last_date = lines[-1].strip() if lines else "无"
            first_date = lines[0].strip() if lines else "无"
        else:
            last_date = first_date = "无日历"

        print(f"  标的数量: {len(stocks)} 只")
        print(f"  日期范围: {first_date} ~ {last_date}")
        for pool in sorted(d.glob("instruments/*.txt")):
            count = len(open(pool).readlines())
            print(f"  股票池 [{pool.stem}]: {count} 只")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Qlib 数据更新器（yfinance）")
    parser.add_argument("--action", choices=["check", "update", "init"],
                        default="check")
    parser.add_argument("--start", default=None, help="开始日期，如 2020-01-01")
    parser.add_argument("--end",   default=None, help="结束日期，默认今天")
    args = parser.parse_args()

    if args.action == "check":
        check_status()
    elif args.action == "update":
        run_update(start=args.start, end=args.end)
    elif args.action == "init":
        start = args.start or "2015-01-01"
        run_init(start=start, end=args.end)
