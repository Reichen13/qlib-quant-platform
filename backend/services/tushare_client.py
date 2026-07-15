"""Tushare 统一客户端 —— token 从环境变量读取，内置 150 次/分钟限流。

设计原则：
- token 永远不在代码/日志里出现明文，统一走 ``TUSHARE_TOKEN`` 环境变量。
- 惰性初始化：首次调用 ``get_pro()`` 才 set_token，无 token 时返回 None，
  调用方据此决定是否降级到其他数据源（baostock / 腾讯）。
- 内置滑动窗口限流，避免全量更新时撞 150 次/分钟上限。
- 日线统一返回"原始价 + adj_factor 复权因子"，与 update_cn_data.py 的
  baostock 写入口径一致（后复权 = raw_price * cumulative_factor）。
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Optional

import pandas as pd
from loguru import logger

# 限流：150 次/分钟，留 10% 余量按 135 计
_RATE_LIMIT_PER_MIN = 135
_RATE_WINDOW_SEC = 60

_call_times: deque[float] = deque()
_lock = threading.Lock()
_pro = None
_pro_initialized = False

# 指数字段映射（tushare 指数接口字段与个股略有不同）
_INDEX_CODE_PREFIX = {"SH": "SH", "SZ": "SZ", "CSI": "CSI"}


def _read_token() -> str:
    """从环境变量读取 token，绝不记录明文。"""
    return os.getenv("TUSHARE_TOKEN", "").strip()


def _read_api_url() -> str:
    """代理站地址；留空用官方默认。"""
    return os.getenv("TUSHARE_API_URL", "").strip()


def is_configured() -> bool:
    """是否配置了 token（用于上层判断 tushare 源是否可用）。"""
    return bool(_read_token())


def _rate_limit_wait() -> None:
    """滑动窗口限流：1 分钟内调用超过上限则 sleep 到最旧调用滑出窗口。"""
    with _lock:
        now = time.monotonic()
        # 清理 60 秒之外的记录
        while _call_times and now - _call_times[0] >= _RATE_WINDOW_SEC:
            _call_times.popleft()
        if len(_call_times) >= _RATE_LIMIT_PER_MIN:
            sleep_for = _RATE_WINDOW_SEC - (now - _call_times[0]) + 0.1
            if sleep_for > 0:
                logger.debug(f"Tushare 限流：等待 {sleep_for:.1f}s")
                time.sleep(sleep_for)
            # 清理过期记录
            now = time.monotonic()
            while _call_times and now - _call_times[0] >= _RATE_WINDOW_SEC:
                _call_times.popleft()
        _call_times.append(now)


def get_pro():
    """返回已初始化的 tushare pro_api 实例；未配置 token 返回 None。

    惰性初始化，进程内只 set_token 一次。
    """
    global _pro, _pro_initialized
    if _pro_initialized:
        return _pro
    _pro_initialized = True
    token = _read_token()
    if not token:
        logger.info("Tushare 未配置 TUSHARE_TOKEN，该数据源不可用")
        return None
    try:
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api()
        url = _read_api_url()
        if url:
            # 代理站地址通过私有属性设置（兼容官方 SDK）
            try:
                pro._DataApi__http_url = url
            except Exception:
                pass
        _pro = pro
        logger.info("Tushare 客户端初始化成功")
    except ImportError:
        logger.warning("tushare 未安装，该数据源不可用")
    except Exception as e:
        logger.warning(f"Tushare 初始化失败: {e}")
    return _pro


def _ts_code_from_yf(yf_code: str) -> str:
    """项目内部 yfinance 码 (600519.SS) -> tushare 码 (600519.SH)。"""
    from utils.code_normalization import normalize_stock_code

    return normalize_stock_code(yf_code, target="tushare")


def fetch_daily(yf_code: str, start: str, end: str) -> pd.DataFrame:
    """获取个股日线（原始价 + adj_factor 复权因子）。

    参数与 update_cn_data.py 现有 fetch_* 一致：
    - yf_code: 600519.SS / SH600519 等项目格式均可（内部归一化）
    - start/end: YYYY-MM-DD
    返回 DataFrame，index 为 YYYY-MM-DD 字符串，列与 baostock 链路对齐：
    open/high/low/close/volume/amount/factor（累积后复权因子）
    """
    pro = get_pro()
    if pro is None:
        return pd.DataFrame()

    ts_code = _ts_code_from_yf(yf_code)
    sd = start.replace("-", "")
    ed = end.replace("-", "")

    try:
        _rate_limit_wait()
        df = pro.daily(ts_code=ts_code, start_date=sd, end_date=ed)
        if df is None or df.empty:
            return pd.DataFrame()

        # tushare trade_date 为 YYYYMMDD，统一转 YYYY-MM-DD 并按日期升序
        df["date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        df = df.sort_values("date").set_index("date")
        df.index = df.index.strftime("%Y-%m-%d")

        # 复权因子：tushare adj_factor 返回每日复权因子，需累积
        _rate_limit_wait()
        adj = pro.adj_factor(ts_code=ts_code, start_date=sd, end_date=ed)
        if adj is not None and not adj.empty:
            adj["date"] = pd.to_datetime(adj["trade_date"], format="%Y%m%d")
            adj = adj.sort_values("date").set_index("date")
            adj.index = adj.index.strftime("%Y-%m-%d")
            df["factor"] = adj["adj_factor"].reindex(df.index).ffill().bfill()
        else:
            df["factor"] = 1.0

        # 口径对齐 baostock 写入链路：OHLC 存复权价 = 原始价 × 累积后复权因子，
        # factor 存累积因子（历史不可变），volume/amount 保持原始口径。
        # 这样下游 append_to_bin 的 _check_overlap_consistency 才能通过。
        out = pd.DataFrame(index=df.index)
        f = pd.to_numeric(df["factor"], errors="coerce").fillna(1.0)
        out["open"] = pd.to_numeric(df["open"], errors="coerce") * f
        out["high"] = pd.to_numeric(df["high"], errors="coerce") * f
        out["low"] = pd.to_numeric(df["low"], errors="coerce") * f
        out["close"] = pd.to_numeric(df["close"], errors="coerce") * f
        out["volume"] = pd.to_numeric(df["vol"], errors="coerce")
        out["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        out["factor"] = f
        return out
    except Exception as e:
        logger.warning(f"Tushare daily 获取失败 {yf_code}: {e}")
        return pd.DataFrame()


def fetch_index_daily(ts_code: str, start: str, end: str) -> pd.DataFrame:
    """获取指数日线（如 000300.SH 沪深300）。返回与 fetch_daily 同结构。"""
    pro = get_pro()
    if pro is None:
        return pd.DataFrame()
    sd = start.replace("-", "")
    ed = end.replace("-", "")
    try:
        _rate_limit_wait()
        df = pro.index_daily(ts_code=ts_code, start_date=sd, end_date=ed)
        if df is None or df.empty:
            return pd.DataFrame()
        df["date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        df = df.sort_values("date").set_index("date")
        df.index = df.index.strftime("%Y-%m-%d")
        out = pd.DataFrame(index=df.index)
        out["open"] = pd.to_numeric(df["open"], errors="coerce")
        out["high"] = pd.to_numeric(df["high"], errors="coerce")
        out["low"] = pd.to_numeric(df["low"], errors="coerce")
        out["close"] = pd.to_numeric(df["close"], errors="coerce")
        out["volume"] = pd.to_numeric(df["vol"], errors="coerce")
        out["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        out["factor"] = 1.0
        return out
    except Exception as e:
        logger.warning(f"Tushare index_daily 获取失败 {ts_code}: {e}")
        return pd.DataFrame()


def fetch_trade_cal(start: str, end: str) -> list[str]:
    """获取交易日历（SSE+SZSE），返回 YYYY-MM-DD 列表。"""
    pro = get_pro()
    if pro is None:
        return []
    sd = start.replace("-", "")
    ed = end.replace("-", "")
    try:
        _rate_limit_wait()
        df = pro.trade_cal(exchange="SSE", start_date=sd, end_date=ed, is_open="1")
        if df is None or df.empty:
            return []
        dates = sorted(df["cal_date"].tolist())
        return [f"{d[:4]}-{d[4:6]}-{d[6:8]}" for d in dates]
    except Exception as e:
        logger.warning(f"Tushare trade_cal 获取失败: {e}")
        return []


def fetch_stock_basic() -> pd.DataFrame:
    """获取全市场股票列表（含北交所）。返回 ts_code/symbol/name/area/industry/list_date。"""
    pro = get_pro()
    if pro is None:
        return pd.DataFrame()
    try:
        _rate_limit_wait()
        return pro.stock_basic(
            exchange="", list_status="L",
            fields="ts_code,symbol,name,area,industry,list_date",
        )
    except Exception as e:
        logger.warning(f"Tushare stock_basic 获取失败: {e}")
        return pd.DataFrame()
