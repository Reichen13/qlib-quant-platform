"""价格口径换算工具。

Qlib $close 存的是后复权价（原始价 × 累积后复权因子）。
面向用户的绝对价格需要换算为前复权价（≈ 真实市价），否则：
- 茅台 K 线显示 9160 元（实际约 1194 元）
- 海龟入场价 9160（实际无法挂单）

换算公式：前复权价 = 后复权价 ÷ 该股最新累积因子
（最新日的 factor 恰好等于后复权价与前复权价的比例）
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
from functools import lru_cache

CN_DATA_DIR = Path.home() / ".qlib" / "qlib_data" / "cn_data"


@lru_cache(maxsize=2048)
def get_latest_factor(code: str) -> float:
    """Read latest real cumulative factor, skipping trailing 1.0 values
    written by Tencent fallback incremental updates."""
    code_lower = code.lower()
    factor_path = CN_DATA_DIR / "features" / code_lower / "factor.day.bin"
    if not factor_path.exists():
        return 1.0
    raw = np.fromfile(str(factor_path), dtype="<f")
    if len(raw) < 2:
        return 1.0
    arr = raw[1:]
    fallback = 1.0
    for i in range(len(arr) - 1, -1, -1):
        val = float(arr[i])
        if not (np.isfinite(val) and val > 0):
            continue
        if val > 1.01:
            return val
        if fallback == 1.0:
            fallback = val
    return fallback


def to_forward_price(back_adj_price: float, code: str) -> float:
    """将后复权价换算为前复权价（≈ 真实市价）。"""
    factor = get_latest_factor(code)
    if factor <= 0:
        return back_adj_price
    return back_adj_price / factor


def to_forward_prices(prices: list[float], code: str) -> list[float]:
    """批量换算后复权价列表为前复权价。"""
    factor = get_latest_factor(code)
    if factor <= 0:
        return prices
    return [p / factor for p in prices]


def get_factor(code: str) -> float:
    """获取最新累积因子（供外部使用）。"""
    return get_latest_factor(code)
