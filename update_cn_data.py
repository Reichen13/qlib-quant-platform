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
import json
import sys
import pathlib
import time
import atexit
import urllib.request

import numpy as np
import pandas as pd
import yfinance as yf

DATA_DIR = pathlib.Path.home() / ".qlib" / "qlib_data" / "cn_data"
FIELDS   = ["open", "close", "high", "low", "volume"]
# amount 和 factor 不在 yfinance，单独处理
EXTRA_FIELDS = ["amount", "factor"]
_BAOSTOCK = None
_BAOSTOCK_LOGGED_IN = False
REBUILD_GAP_THRESHOLD = 500
REQUEST_SLEEP_SECONDS = 0.05


# ── 日历 ──

def load_calendar() -> list[str]:
    cal_path = DATA_DIR / "calendars" / "day.txt"
    with open(cal_path) as f:
        return [l.strip() for l in f if l.strip()]


def _normalize_calendar_dates(dates: list[str]) -> list[str]:
    return sorted(dict.fromkeys(str(d).strip() for d in dates if str(d).strip()))


def _write_calendar(dates: list[str]) -> None:
    cal_path = DATA_DIR / "calendars" / "day.txt"
    normalized = _normalize_calendar_dates(dates)
    with open(cal_path, "w", encoding="utf-8") as f:
        f.write("\n".join(normalized))
        if normalized:
            f.write("\n")


def extend_calendar(new_dates: list[str]) -> list[str]:
    """把新交易日追加到日历"""
    old_cal = load_calendar()
    normalized_old = _normalize_calendar_dates(old_cal)
    if normalized_old != old_cal:
        raise ValueError("日历只能尾部追加；当前 day.txt 存在乱序或重复，请先全量重建后再更新")

    calendar = list(old_cal)
    added = []
    seen = set(calendar)
    last_date = calendar[-1] if calendar else None
    for date in _normalize_calendar_dates(new_dates):
        if date in seen:
            continue
        if last_date and date <= last_date:
            raise ValueError("日历只能尾部追加；检测到中段插入或重排，请先全量重建后再更新")
        calendar.append(date)
        seen.add(date)
        added.append(date)
        last_date = date

    if added:
        _write_calendar(calendar)
        print(f"  日历新增 {len(added)} 天，最新: {calendar[-1]}")
    return calendar


# ── 代码转换 ──

def qlib_to_yf(code: str) -> str:
    """sh600519 → 600519.SS，sz000001 → 000001.SZ，bj430047 → 430047.BJ"""
    code = code.lower()
    if code.startswith("sh"):
        return code[2:].upper() + ".SS"
    elif code.startswith("sz"):
        return code[2:].upper() + ".SZ"
    elif code.startswith("bj"):
        return code[2:].upper() + ".BJ"
    return code.upper() + ".SS"


def yf_to_baostock(code: str) -> str:
    """600519.SS → sh.600519，000001.SZ → sz.000001，430047.BJ → bj.430047"""
    code = code.upper()
    if code.endswith(".SS"):
        return "sh." + code[:6]
    if code.endswith(".SZ"):
        return "sz." + code[:6]
    if code.endswith(".BJ"):
        return "bj." + code[:6]
    if code.startswith("SH"):
        return "sh." + code[2:8]
    if code.startswith("SZ"):
        return "sz." + code[2:8]
    if code.startswith("BJ"):
        return "bj." + code[2:8]
    return "sh." + code[:6]


def _get_baostock():
    global _BAOSTOCK, _BAOSTOCK_LOGGED_IN
    if _BAOSTOCK_LOGGED_IN:
        return _BAOSTOCK

    import baostock as bs

    lg = bs.login()
    if lg.error_code != "0":
        print(f"  WARN: Baostock 登录失败: {lg.error_code} {lg.error_msg}")
        return None

    _BAOSTOCK = bs
    _BAOSTOCK_LOGGED_IN = True
    return bs


def _logout_baostock():
    global _BAOSTOCK_LOGGED_IN
    if _BAOSTOCK_LOGGED_IN and _BAOSTOCK is not None:
        try:
            _BAOSTOCK.logout()
        except Exception:
            pass
        _BAOSTOCK_LOGGED_IN = False


atexit.register(_logout_baostock)


# ── 行情拉取 ──

def fetch_yfinance(yf_code: str, start: str, end: str) -> pd.DataFrame:
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
    except Exception as e:
        print(f"  WARN: yfinance 获取 {yf_code} 失败: {e}")
        return pd.DataFrame()


def _query_baostock_history(bs, yf_code: str, start: str, end: str, adjustflag: str) -> pd.DataFrame:
    rs = bs.query_history_k_data_plus(
        yf_to_baostock(yf_code),
        "date,code,open,high,low,close,volume,amount,tradestatus",
        start_date=start,
        end_date=end,
        frequency="d",
        adjustflag=adjustflag,
    )
    if rs.error_code != "0":
        print(f"  WARN: Baostock 获取 {yf_code} 失败: {rs.error_code} {rs.error_msg}")
        return pd.DataFrame()

    rows = []
    while rs.next():
        row = rs.get_row_data()
        # baostock 对停牌日返回 tradestatus!=1 的行（close 为前值假行情），
        # 必须过滤掉，否则停牌期被当成正常交易日写入 bin
        if len(row) >= 9 and row[8] != "1":
            continue
        rows.append(row[:8])  # 去掉 tradestatus 列，保持原 8 列结构
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        rows,
        columns=["date", "code", "open", "high", "low", "close", "volume", "amount"],
    )
    df.index = df["date"].astype(str)
    for field in FIELDS + ["amount"]:
        df[field] = pd.to_numeric(df[field], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    return df[[f for f in FIELDS + ["amount"] if f in df.columns]]


def _query_baostock_adjust_factor(bs, yf_code: str, start: str, end: str) -> pd.DataFrame:
    """拉取 baostock 累积复权因子表。

    baostock query_adjust_factor 返回字段：
    code / dividOperateDate / foreAdjustFactor / backAdjustFactor / adjustFactor。
    backAdjustFactor 即后复权累积因子（历史不可变）。
    """
    rs = bs.query_adjust_factor(
        code=yf_to_baostock(yf_code),
        start_date=start,
        end_date=end,
    )
    if getattr(rs, "error_code", "0") != "0":
        print(f"  WARN: Baostock 复权因子获取 {yf_code} 失败: {getattr(rs, 'error_code', '')} {getattr(rs, 'error_msg', '')}")
        return pd.DataFrame()

    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return pd.DataFrame()

    columns = getattr(rs, "fields", None) or [
        "code", "dividOperateDate", "foreAdjustFactor", "backAdjustFactor", "adjustFactor",
    ]
    df = pd.DataFrame(rows, columns=list(columns))
    return df


def _build_cumulative_back_factor(factor_rows: pd.DataFrame, raw_index: pd.Index) -> pd.Series:
    """根据除权事件表构造按交易日的后复权累积因子序列（阶梯函数）。

    baostock backAdjustFactor 本身就是"从上市日起的累积后复权因子"（实测单调
    递增），因此每个事件日的值可直接使用，**不能再连乘**。构造方式为阶梯函数：
    - 每个交易日取"日期 ≤ 该日的最近一次事件的 backAdjustFactor 值"；
    - 首个事件之前为 1.0（尚未发生除权）。
    """
    base = pd.Series(1.0, index=raw_index)
    if factor_rows is None or factor_rows.empty:
        return base

    col = "backAdjustFactor" if "backAdjustFactor" in factor_rows.columns else "adjustFactor"
    events = factor_rows[["dividOperateDate", col]].copy()
    events["dividOperateDate"] = events["dividOperateDate"].astype(str)
    events[col] = pd.to_numeric(events[col], errors="coerce")
    events = events.dropna().sort_values("dividOperateDate")

    # 阶梯函数：每个日期取"≤ 该日的最近一次事件的累积因子值"
    # baostock 返回值已是累积值，直接查找，不做乘法
    event_dates = events["dividOperateDate"].tolist()
    event_values = events[col].tolist()
    for i in range(len(base)):
        current_date = str(base.index[i])
        # 找到 <= current_date 的最后一个事件
        applicable = None
        for event_date, event_value in zip(event_dates, event_values):
            if event_date <= current_date:
                applicable = event_value
            else:
                break
        if applicable is not None:
            base.iloc[i] = float(applicable)
    return base


def fetch_baostock(yf_code: str, start: str, end: str) -> pd.DataFrame:
    """写入链路唯一数据源：baostock 原始价 + 累积后复权因子。

    存储口径（与 Qlib bin 约定一致）：
      - close/open/high/low 存复权价 = 原始价 × 累积后复权因子
      - factor 存累积后复权因子（历史不可变，新除权只影响新增行）
    这样下游读 $close 直接拿到后复权序列，读 $close/$factor 还原原始价。
    """
    try:
        bs = _get_baostock()
        if bs is None:
            return pd.DataFrame()

        # 1. 原始价（不复权）
        raw_df = _query_baostock_history(bs, yf_code, start, end, adjustflag="3")
        if raw_df.empty:
            return pd.DataFrame()

        # 2. 累积后复权因子表（查询窗口固定从上市日起，与抓取窗口无关）
        #    否则增量更新窗口内无除权事件 → factor=1.0 → 追加段断层
        factor_rows = _query_baostock_adjust_factor(bs, yf_code, "1990-01-01", end)
        cumulative_factor = _build_cumulative_back_factor(factor_rows, raw_df.index)

        # 3. 组装：OHLC 复权价 = 原始价 × 累积因子；volume/amount 保持原始口径
        df = raw_df.copy()
        for field in ("open", "close", "high", "low"):
            if field in df.columns:
                df[field] = df[field] * cumulative_factor.values
        df["factor"] = cumulative_factor.values
        return df[[f for f in FIELDS + EXTRA_FIELDS if f in df.columns]]
    except Exception as e:
        print(f"  WARN: Baostock 获取 {yf_code} 失败: {e}")
        return pd.DataFrame()


def yf_to_eastmoney_secid(code: str) -> str:
    code = code.upper()
    if code.endswith(".SS"):
        return "1." + code[:6]
    if code.endswith(".SZ"):
        return "0." + code[:6]
    if code.endswith(".BJ"):
        return "0." + code[:6]
    if code.startswith("SH"):
        return "1." + code[2:8]
    if code.startswith("SZ") or code.startswith("BJ"):
        return "0." + code[2:8]
    return "1." + code[:6]


def fetch_eastmoney(yf_code: str, start: str, end: str) -> pd.DataFrame:
    try:
        secid = yf_to_eastmoney_secid(yf_code)
        beg = start.replace("-", "")
        end_ = end.replace("-", "")
        url = (
            "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
            "&fields2=f51,f52,f53,f54,f55,f56,f57"
            f"&klt=101&fqt=1&beg={beg}&end={end_}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
                ),
                "Referer": "https://quote.eastmoney.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        klines = (payload.get("data") or {}).get("klines") or []
        rows = []
        for item in klines:
            parts = item.split(",")
            if len(parts) >= 7:
                rows.append(parts[:7])
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(
            rows,
            columns=["date", "open", "close", "high", "low", "volume", "amount"],
        )
        df.index = df["date"].astype(str)
        for field in FIELDS + ["amount"]:
            df[field] = pd.to_numeric(df[field], errors="coerce")
        df["factor"] = 1.0
        df = df.dropna(subset=["open", "high", "low", "close"])
        return df[[f for f in FIELDS + EXTRA_FIELDS if f in df.columns]]
    except Exception as e:
        print(f"  WARN: Eastmoney fetch {yf_code} failed: {e}")
        return pd.DataFrame()


def yf_to_tencent_code(code: str) -> str:
    code = code.upper()
    if code.endswith(".SS"):
        return "sh" + code[:6]
    if code.endswith(".SZ"):
        return "sz" + code[:6]
    if code.endswith(".BJ"):
        return "bj" + code[:6]
    if code.startswith(("SH", "SZ", "BJ")):
        return code[:2].lower() + code[2:8]
    return "sh" + code[:6]


def fetch_tencent(yf_code: str, start: str, end: str) -> pd.DataFrame:
    try:
        tencent_code = yf_to_tencent_code(yf_code)
        url = (
            "https://web.ifzq.gtimg.cn/appstock/app/kline/kline"
            f"?param={tencent_code},day,{start},{end},640"
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
                ),
                "Referer": "https://gu.qq.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        data = (payload.get("data") or {}).get(tencent_code) or {}
        rows = data.get("qfqday") or data.get("day") or []
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(
            [row[:6] for row in rows if len(row) >= 6],
            columns=["date", "open", "close", "high", "low", "volume"],
        )
        if df.empty:
            return pd.DataFrame()

        df.index = df["date"].astype(str)
        for field in FIELDS:
            df[field] = pd.to_numeric(df[field], errors="coerce")
        df["volume"] = df["volume"] * 100.0
        df["amount"] = df["close"] * df["volume"]
        df["factor"] = 1.0
        df = df.dropna(subset=["open", "high", "low", "close"])
        return df[[f for f in FIELDS + EXTRA_FIELDS if f in df.columns]]
    except Exception as e:
        print(f"  WARN: Tencent fetch {yf_code} failed: {e}")
        return pd.DataFrame()


def fetch(yf_code: str, start: str, end: str) -> pd.DataFrame:
    """写入链路只能使用 baostock（同时具备原始价与累积复权因子）。

    腾讯/东财只提供前复权、yfinance auto_adjust 含分红全收益回调，三者
    在"原始价 + 因子"口径下均无法给出正确输入，故不再进入写入链路；
    它们保留为 fetch_tencent/fetch_eastmoney/fetch_yfinance，仅用于校验对照。
    """
    return fetch_baostock(yf_code, start, end)


def _clip_to_requested_range(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Keep only rows that fall inside the requested inclusive date window."""
    if not isinstance(df, pd.DataFrame):
        return df
    if df.empty:
        return df

    index = pd.to_datetime(df.index, errors="coerce")
    mask = (index >= pd.Timestamp(start)) & (index <= pd.Timestamp(end))
    clipped = df.loc[mask].copy()
    clipped.index = pd.Index([ts.strftime("%Y-%m-%d") for ts in pd.to_datetime(clipped.index)])
    return clipped


# ── Qlib bin 追加 ──

def _date_to_calendar_index(calendar_index: dict[str, int], date_str: str) -> int | None:
    return calendar_index.get(str(date_str))


def _write_bin(bin_path: pathlib.Path, start_idx: int, values: list[float]):
    payload = np.array([float(start_idx), *values], dtype="<f")
    with open(bin_path, "wb") as fp:
        payload.tofile(fp)


def _should_rebuild_bin(end_idx: int, first_new_idx: int, raw_len: int, rebuild_stale: bool) -> bool:
    if not rebuild_stale:
        return False
    if first_new_idx <= end_idx:
        return False
    return first_new_idx - end_idx > REBUILD_GAP_THRESHOLD and raw_len < REBUILD_GAP_THRESHOLD


def _repair_existing_stale_values(
    bin_path: pathlib.Path,
    raw: np.ndarray,
    start_idx: int,
    end_idx: int,
    df: pd.DataFrame,
    field: str,
    calendar_index: dict[str, int],
    rebuild_stale: bool,
    overwrite_existing: bool = False,
) -> int:
    if not rebuild_stale and not overwrite_existing:
        return 0

    values = raw[1:].copy()
    repaired = 0
    for date_str in df.index:
        cal_idx = _date_to_calendar_index(calendar_index, date_str)
        if cal_idx is None or cal_idx < start_idx or cal_idx > end_idx:
            continue

        new_val = float(df.loc[date_str, field])
        if not np.isfinite(new_val) or new_val == 0:
            continue

        pos = cal_idx - start_idx
        old_val = values[pos]
        should_repair_stale = not np.isfinite(old_val) or old_val == 0
        # 新方案下 factor 是真实累积因子，--overwrite-existing 重建单票时必须允许重写 factor，
        # 否则修完的票 $close/$factor 还原出错价、健康检查的占位检测也消不掉。
        should_overwrite = overwrite_existing and abs(float(old_val) - new_val) > 1e-8
        if should_repair_stale or should_overwrite:
            values[pos] = new_val
            repaired += 1

    if repaired:
        _write_bin(bin_path, start_idx, values.tolist())

    return repaired


def _check_overlap_consistency(
    qlib_code: str,
    df: pd.DataFrame,
    calendar: list[str],
    threshold: float = 0.005,
    rebuild_stale: bool = False,
    overwrite_existing: bool = False,
) -> str | None:
    """比对追加段与现有 close.bin 的重叠日，相对偏差 >threshold 返回告警文案（重建模式跳过）。

    用途：拦截新旧口径混拼（例如对旧前复权目录误跑后复权增量更新），或未来
    任何来源/口径漂移。重建模式（rebuild_stale/overwrite_existing）下不拦截，
    因为重写本就是预期行为。返回 None 表示一致；返回字符串表示应拒绝追加。
    """
    if rebuild_stale or overwrite_existing:
        return None
    if "close" not in df.columns:
        return None

    stock_dir = DATA_DIR / "features" / qlib_code.lower()
    close_path = stock_dir / "close.day.bin"
    if not close_path.exists():
        return None

    raw = np.fromfile(close_path, dtype="<f")
    if len(raw) < 2:
        return None

    start_idx = int(raw[0])
    existing_len = len(raw) - 1
    end_idx = start_idx + existing_len - 1
    calendar_index = {date: idx for idx, date in enumerate(calendar)}

    overlap_checks = 0
    for date_str in df.index:
        cal_idx = _date_to_calendar_index(calendar_index, date_str)
        if cal_idx is None or cal_idx > end_idx or cal_idx < start_idx:
            continue
        existing_val = float(raw[1 + (cal_idx - start_idx)])
        new_val = float(df.loc[date_str, "close"])
        if not np.isfinite(existing_val) or existing_val == 0:
            continue
        if not np.isfinite(new_val) or new_val == 0:
            continue
        overlap_checks += 1
        rel_diff = abs(new_val - existing_val) / abs(existing_val)
        if rel_diff > threshold:
            return (
                f"重叠日 {date_str} close 相对偏差 {rel_diff:.2%} 超过 {threshold:.2%}，"
                f"疑似口径不一致（新旧复权混拼），需全量重建"
            )

    if overlap_checks == 0:
        # 不拦截合法增量（最新日+1 起本就无重叠），但打印提示，避免校验形同虚设
        print(
            f"  WARN {qlib_code}: 抓取窗口与现有数据无重叠日，重叠校验未生效；"
            "请确认增量起始日取的是'最新有效日本身'（有重叠）而非其后一天"
        )
    return None


def append_to_bin(
    qlib_code: str,
    df: pd.DataFrame,
    calendar: list[str],
    rebuild_stale: bool = False,
    overwrite_existing: bool = False,
) -> int:
    """把 df 追加到已有 bin 文件，返回追加的行数"""
    if df.empty:
        return 0

    # 新旧口径混拼拦截：比对重叠日 close，相对偏差 >0.5% 拒绝追加
    consistency = _check_overlap_consistency(
        qlib_code,
        df,
        calendar,
        rebuild_stale=rebuild_stale,
        overwrite_existing=overwrite_existing,
    )
    if consistency is not None:
        print(f"  SKIP {qlib_code}: {consistency}")
        return 0

    # 只保留日历里有的日期
    cal_set = set(calendar)
    calendar_index = {date: idx for idx, date in enumerate(calendar)}
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

        repaired = _repair_existing_stale_values(
            bin_path,
            raw,
            start_idx,
            end_idx,
            df,
            field,
            calendar_index,
            rebuild_stale,
            overwrite_existing,
        )
        appended = max(appended, repaired)

        # 找新数据中日历索引 > end_idx 的部分
        new_rows = []
        for date_str in df.index:
            cal_idx = _date_to_calendar_index(calendar_index, date_str)
            if cal_idx is None:
                continue
            if cal_idx > end_idx:
                new_rows.append((cal_idx, float(df.loc[date_str, field])))

        if not new_rows:
            continue

        # 排序，中间缺失的日期填 NaN
        new_rows.sort()
        if _should_rebuild_bin(end_idx, new_rows[0][0], len(raw), rebuild_stale):
            _write_bin(bin_path, new_rows[0][0], [val for _, val in new_rows])
            appended = max(appended, len(new_rows))
            continue

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


def full_rebuild_stock(
    qlib_code: str,
    df: pd.DataFrame,
    calendar: list[str],
) -> int:
    """从零构造完整 bin（--full-rebuild 模式专用）。

    与 append_to_bin/repair 的本质区别：
      - 不依赖旧 bin 的 start_idx（旧 bin 可能因日历错位而索引错误）；
      - 从 df 最早交易日重新计算 start_idx；
      - 按日历逐日填值，缺失日填 NaN，七个字段整文件覆盖写。

    返回写入的字段数。
    """
    if df.empty or not calendar:
        return 0

    calendar_index = {date: idx for idx, date in enumerate(calendar)}
    cal_set = set(calendar)
    df = df[[d in cal_set for d in df.index]]
    if df.empty:
        return 0

    stock_dir = DATA_DIR / "features" / qlib_code.lower()
    stock_dir.mkdir(parents=True, exist_ok=True)

    # 新 start_idx = df 最早交易日在日历中的索引
    first_date = str(min(df.index))
    start_idx = calendar_index[first_date]
    # 末尾覆盖到日历最后一天（全量序列）
    end_idx = len(calendar) - 1
    length = end_idx - start_idx + 1

    written = 0
    for field in FIELDS + EXTRA_FIELDS:
        if field not in df.columns:
            continue
        # 按日历逐日构造完整序列，缺失填 NaN
        values: list[float] = [float("nan")] * length
        for date_str, val in df[field].items():
            cal_idx = _date_to_calendar_index(calendar_index, date_str)
            if cal_idx is None or cal_idx < start_idx:
                continue
            offset = cal_idx - start_idx
            values[offset] = float(val)
        # factor 是阶梯函数：停牌/缺失期间值已知（延续前值），不填 NaN
        # 避免 $close/$factor 在停牌邻近日出现不必要的 NaN 传播
        if field == "factor":
            last_val = float("nan")
            for i in range(length):
                import math
                if math.isfinite(values[i]):
                    last_val = values[i]
                elif math.isfinite(last_val):
                    values[i] = last_val

        bin_path = stock_dir / f"{field}.day.bin"
        _write_bin(bin_path, start_idx, values)
        written += 1

    return written


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


def update(
    start: str = "2020-09-26",
    end: str = None,
    max_stocks: int = None,
    codes: list[str] | None = None,
    full_rebuild: bool = False,
    rebuild_stale: bool = False,
    overwrite_existing: bool = False,
) -> int:
    if end is None:
        end = (pd.Timestamp.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    if full_rebuild:
        start = "1990-01-01"  # 重建模式从上市日起拉，覆盖完整历史
    elif start == "2020-09-26":
        # 增量默认：用最新有效日本身（有重叠），让混拼防护每次真实校验一个重叠日
        last_eff = _get_market_last_effective_date()
        start = _resolve_incremental_start(last_eff)

    mode = "全量重建" if full_rebuild else "增量更新"
    print(f"=== {mode} {start} ~ {end} ===")
    print(f"  数据目录: {DATA_DIR}")

    if full_rebuild:
        _init_rebuild_skeleton(codes)

    # 1. 日历准备
    print("\n[1] 准备交易日历...")
    calendar = load_calendar() if full_rebuild else []
    if full_rebuild and not calendar:
        print("  ERROR: 重建模式需要 baostock 重建的完整日历，但当前为空")
        return 2
    if not full_rebuild or not calendar:
        # 增量模式，或重建模式日历缺失时，用沪深300ETF 拉新交易日扩展日历
        ref_df = fetch("510300.SS", start, end)  # noqa: ETF 仅用于增量日历扩展，不写入
        ref_df = _clip_to_requested_range(ref_df, start, end)
        if ref_df.empty and not calendar:
            print("  ERROR: 无法获取参考数据，请检查网络")
            return 2
        if not ref_df.empty:
            new_dates = list(ref_df.index)
            calendar = extend_calendar(new_dates)
            print(f"  新增交易日: {new_dates[0]} ~ {new_dates[-1]}  ({len(new_dates)} 天)")

    # 2. 获取股票列表
    if full_rebuild:
        # 重建模式：按 codes 列表，不依赖现有 features 目录
        if not codes:
            print("  ERROR: --full-rebuild 必须配合 --code 或 --codes-file 指定股票")
            return 3
        stocks = [pathlib.Path(c.lower()) for c in codes]
    else:
        stocks = sorted(DATA_DIR.glob("features/*/close.day.bin"))
        if codes:
            wanted = {code.lower() for code in codes}
            stocks = [path for path in stocks if path.parent.name.lower() in wanted]
        if max_stocks:
            stocks = stocks[:max_stocks]
    total = len(stocks)
    if total == 0:
        print("  ERROR: 未找到可更新的股票特征文件，请检查 Qlib 数据目录")
        return 3
    print(f"\n[2] 开始更新 {total} 只股票...")

    success = skip = fail = 0
    start_time = time.time()

    for i, bin_path in enumerate(stocks):
        qlib_code = bin_path.name if full_rebuild else bin_path.parent.name
        yf_code = qlib_to_yf(qlib_code)

        # 拉取新数据
        df = fetch(yf_code, start, end)
        df = _clip_to_requested_range(df, start, end)

        if df.empty:
            fail += 1
        else:
            if full_rebuild:
                appended = full_rebuild_stock(qlib_code, df, calendar)
            else:
                appended = append_to_bin(
                    qlib_code,
                    df,
                    calendar,
                    rebuild_stale=rebuild_stale,
                    overwrite_existing=overwrite_existing,
                )
            if appended > 0:
                success += 1
            else:
                skip += 1

        # 进度
        if (i + 1) % 50 == 0 or i == total - 1:
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (total - i - 1) / speed if speed > 0 else 0
            print(f"  [{i+1}/{total}] 成功:{success} 跳过:{skip} 失败:{fail} "
                  f"速度:{speed:.1f}只/s 剩余:{remaining/60:.1f}分")

        time.sleep(REQUEST_SLEEP_SECONDS)  # 限速避免被封

    if success == 0 and skip == 0 and fail > 0:
        print("  ERROR: 所有股票数据拉取失败，请检查行情源或网络")
        return 4

    # 3. instruments 日期范围
    if full_rebuild:
        print("\n[3] 重建模式：只写小样本 instruments")
        ipo_map = _query_ipo_dates(codes)
        _write_sample_instruments(codes, calendar[-1], ipo_map=ipo_map)
    elif max_stocks is None and not codes:
        print("\n[3] 更新股票池日期范围...")
        _update_instruments_end(calendar[-1])
    else:
        print("\n[3] 小范围更新，跳过全量股票池日期范围写入")

    elapsed = time.time() - start_time
    print(f"\n完成！耗时 {elapsed/60:.1f} 分钟")
    print(f"成功: {success}  跳过(无新数据): {skip}  失败: {fail}")
    print(f"数据最新日期: {calendar[-1]}")
    return 0


def _update_instruments_end(new_end: str):
    """把所有 instruments 文件的结束日期更新到 new_end"""
    for inst_path in (DATA_DIR / "instruments").glob("*.txt"):
        with open(inst_path, encoding="utf-8") as fp:
            lines = fp.readlines()
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


# ── 增量起始日 ──

def _resolve_incremental_start(last_effective_date: str) -> str:
    """增量默认起始日 = 最新有效日本身（有重叠），而非其后一天。

    多拉一天零成本，但让 _check_overlap_consistency 每次能真实校验一个重叠日，
    否则混拼防护对正常增量永远只剩一条 warning。无有效日时回退 2020-09-26。
    """
    last_effective_date = (last_effective_date or "").strip()
    return last_effective_date if last_effective_date else "2020-09-26"


def _get_market_last_effective_date() -> str:
    """读本机全市场 close.day.bin 的代表性最新有效日（用于增量默认 start）。"""
    try:
        cal = load_calendar()
        if not cal:
            return ""
        # 抽样：取 features 目录前若干只 close.bin 的末日索引对应日期的中位数
        dates = []
        for close_path in sorted(DATA_DIR.glob("features/*/close.day.bin"))[:50]:
            raw = np.fromfile(close_path, dtype="<f")
            if len(raw) < 2:
                continue
            # 从末尾往前找第一个有限且>0的值
            for offset in range(len(raw) - 1, 0, -1):
                val = float(raw[offset])
                if np.isfinite(val) and val > 0:
                    end_idx = int(raw[0]) + (offset - 1)
                    if 0 <= end_idx < len(cal):
                        dates.append(cal[end_idx])
                    break
        if not dates:
            return ""
        dates.sort()
        return dates[len(dates) // 2]
    except Exception:
        return ""


def _rebuild_calendar_from_baostock(start: str = "1990-01-01", end: str | None = None) -> list[str]:
    """用 baostock query_trade_dates 全量重建官方交易日历。

    旧源日历经审计发现有成段缺失（如 2016 春节段缺 16 个交易日），
    不能直接复制——会导致 df 被静默丢弃这些日期的数据，并制造跨洞收益率。
    """
    if end is None:
        end = (pd.Timestamp.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        bs = _get_baostock()
        if bs is None:
            return []
        rs = bs.query_trade_dates(start_date=start, end_date=end)
        if rs.error_code != "0":
            print(f"  WARN: query_trade_dates 失败: {rs.error_code} {rs.error_msg}")
            return []
        trading_days = []
        while rs.next():
            row = rs.get_row_data()  # calendar_date, is_trading_day
            if len(row) >= 2 and row[1] == "1":
                trading_days.append(row[0])
        return trading_days
    except Exception as e:
        print(f"  WARN: 从 baostock 重建日历失败: {e}")
        return []


def _init_rebuild_skeleton(codes: list[str] | None) -> None:
    """初始化重建目录骨架：日历用 baostock query_trade_dates 全量重建（旧源日历有洞，
    不能复制），instruments/features 目录创建空。"""
    dst_cal = DATA_DIR / "calendars" / "day.txt"
    dst_cal.parent.mkdir(parents=True, exist_ok=True)

    if dst_cal.exists():
        print(f"  日历已存在: {dst_cal}（跳过重建）")
    else:
        print("  从 baostock query_trade_dates 重建官方交易日历...")
        days = _rebuild_calendar_from_baostock()
        if days:
            dst_cal.write_text("\n".join(days) + "\n", encoding="utf-8")
            print(f"  日历重建完成: {days[0]} ~ {days[-1]} ({len(days)} 天)")
        else:
            print(f"  WARN: 日历重建失败，将在拉取时扩展")

    (DATA_DIR / "instruments").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "features").mkdir(parents=True, exist_ok=True)


def _query_ipo_dates(codes: list[str]) -> dict[str, str]:
    """查 baostock query_stock_basic 拿真实上市日（ipoDate）。失败返回空映射。"""
    ipo_map: dict[str, str] = {}
    try:
        bs = _get_baostock()
        if bs is None:
            return ipo_map
        for qlib_code in codes:
            rs = bs.query_stock_basic(code=yf_to_baostock(qlib_to_yf(qlib_code)))
            if getattr(rs, "error_code", "0") != "0":
                continue
            while rs.next():
                row = rs.get_row_data()
                # fields: code, code_name, ipoDate, outDate, type, status
                if len(row) >= 3 and row[2]:
                    ipo_map[qlib_code.lower()] = row[2]
                    break
    except Exception as e:
        print(f"  WARN: 查询上市日失败，instruments 将回退到 2014-01-01: {e}")
    return ipo_map


def _write_sample_instruments(
    codes: list[str] | None,
    new_end: str,
    ipo_map: dict[str, str] | None = None,
) -> None:
    """重建模式下只写小样本 instruments/all.txt，验收通过后再扩全量。

    起始日用真实上市日（ipo_map[code]），缺失时回退 2014-01-01。
    """
    if not codes:
        return
    ipo_map = ipo_map or {}
    inst_path = DATA_DIR / "instruments" / "all.txt"
    lines = []
    for code in codes:
        start = ipo_map.get(code.lower(), "2014-01-01")
        lines.append(f"{code.lower()}\t{start}\t{new_end}")
    inst_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  {inst_path.name}: {len(lines)} 只小样本")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check",  action="store_true", help="只检查状态")
    parser.add_argument("--start",  default="2020-09-26", help="起始日期")
    parser.add_argument("--end",    default=None,         help="结束日期")
    parser.add_argument("--max",    type=int, default=None, help="最多更新几只（测试用）")
    parser.add_argument("--code", action="append", default=None, help="只更新指定 Qlib 代码，可重复传入，如 --code sz300750")
    parser.add_argument("--codes-file", default=None, help="只更新文件中列出的 Qlib 代码，每行一个")
    parser.add_argument("--data-dir", default=None, help="数据目录（默认 ~/.qlib/qlib_data/cn_data）；重建时指定 cn_data_new")
    parser.add_argument("--full-rebuild", action="store_true", help="全量重建模式：从 df 从零构造完整 bin，不走 repair+append；须配合 --data-dir 指向新目录")
    parser.add_argument("--rebuild-stale", action="store_true", help="重建明显异常的短历史文件，用于修复少量核心股票缺口")
    parser.add_argument("--overwrite-existing", action="store_true", help="覆盖指定日期窗口内已有的非 0 价格/成交/factor 字段（新方案 factor 为真实累积因子，重建单票时需一并重写）")
    args = parser.parse_args()

    if args.data_dir:
        DATA_DIR = pathlib.Path(args.data_dir)
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.check:
        check()
    else:
        codes = list(args.code or [])
        if args.codes_file:
            codes.extend(
                line.strip()
                for line in pathlib.Path(args.codes_file).read_text().splitlines()
                if line.strip()
            )
        sys.exit(
            update(
                start=args.start,
                end=args.end,
                max_stocks=args.max,
                codes=codes or None,
                full_rebuild=args.full_rebuild,
                rebuild_stale=args.rebuild_stale,
                overwrite_existing=args.overwrite_existing,
            )
        )
