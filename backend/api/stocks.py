"""
股票相关 API
"""

from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from backend.models.schemas import (
    StockInfo, StockListResponse, ApiResponse
)

router = APIRouter()

# 导入核心模块
import sys
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ── 完整股票名称缓存（启动时加载，后续纯内存查询） ──
_full_name_cache: dict = {}
_cache_loaded = False


def _get_market(code: str) -> str:
    """Return exchange prefix for Qlib-style or plain A-share codes."""
    code_upper = code.upper().strip()
    if code_upper.startswith("SH"):
        return "SH"
    if code_upper.startswith("SZ"):
        return "SZ"
    return "SH" if code_upper.startswith(("6", "5")) else "SZ"


def _load_stock_names():
    """加载 CSI300 完整股票名称映射（仅首次调用时从 baostock 获取，之后纯内存）"""
    global _full_name_cache, _cache_loaded
    if _cache_loaded:
        return _full_name_cache

    # 方法1: 用 baostock 获取（快速本地接口）
    try:
        import baostock as bs
        bs.login()
        rs = bs.query_hs300_stocks()
        while (rs.error_code == '0') and rs.next():
            row = rs.get_row_data()
            code = row[1].replace('.', '').upper()
            name = row[2]
            _full_name_cache[code] = name
        bs.logout()
        logger.info(f"从 baostock 加载了 {len(_full_name_cache)} 只 CSI300 股票名称")
    except Exception as e:
        logger.warning(f"baostock 加载失败: {e}")

    # 方法2: 补充 csi300.txt 中 baostock 没有的
    csi300_file = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "instruments" / "csi300.txt"
    if csi300_file.exists():
        with open(csi300_file) as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 1:
                    code = parts[0].upper()
                    if code not in _full_name_cache:
                        _full_name_cache[code] = code

    _cache_loaded = True
    return _full_name_cache


@router.get("/search")
async def search_stocks(q: str = Query(..., min_length=1, description="搜索关键词")):
    """
    搜索股票（纯内存查询，毫秒级响应）
    """
    name_map = _load_stock_names()
    results = []
    query_lower = q.lower()

    for code, name in name_map.items():
        code_lower = code.lower()
        name_lower = name.lower()
        pure_code = code_lower.replace("sh", "").replace("sz", "")

        if (query_lower in code_lower or
            query_lower in name_lower or
            query_lower in pure_code):

            market = _get_market(code)

            results.append({
                "code": code,
                "name": name,
                "market": market,
            })

            if len(results) >= 20:
                break

    return {"total": len(results), "results": results}


@router.get("/list")
async def get_stock_list():
    """
    获取股票列表（CSI300 成分股）
    """
    name_map = _load_stock_names()
    stocks = []

    for code, name in name_map.items():
        market = _get_market(code)
        stocks.append(StockInfo(
            code=code,
            name=name,
            market=market,
            transparency="MEDIUM"  # 搜索/列表不需要调用 yfinance
        ))

    return StockListResponse(total=len(stocks), stocks=stocks)


@router.get("/{code}")
async def get_stock_info(code: str):
    """
    获取单个股票信息
    """
    name_map = _load_stock_names()
    code_upper = code.upper().strip()

    if not code_upper.startswith(("SH", "SZ")):
        if code_upper.startswith("6") or code_upper.startswith("5"):
            code_upper = f"SH{code_upper}"
        else:
            code_upper = f"SZ{code_upper}"

    name = name_map.get(code_upper, code_upper)
    market = _get_market(code_upper)

    return StockInfo(
        code=code_upper,
        name=name,
        market=market,
        transparency="MEDIUM"
    )
