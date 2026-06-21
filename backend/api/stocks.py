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
    if code_upper.startswith("BJ"):
        return "BJ"
    return "SH" if code_upper.startswith(("6", "5")) else "SZ"


def _to_api_code(bs_or_qlib_code: str) -> str:
    code = bs_or_qlib_code.upper().strip()
    if code.startswith("SH.") or code.startswith("SZ.") or code.startswith("BJ."):
        return code.replace(".", "")
    if code.startswith("SH") or code.startswith("SZ") or code.startswith("BJ"):
        return code
    if code.startswith("6") or code.startswith("5"):
        return f"SH{code[-6:]}"
    if code.startswith(("4", "8")) or code.startswith("920"):
        return f"BJ{code[-6:]}"
    return f"SZ{code[-6:]}"


def _load_stock_names_from_provider() -> dict:
    try:
        from services.data_provider import DataProvider

        provider = DataProvider()
        all_stocks = provider.get_all_stocks()
        names = {}
        for stock in all_stocks:
            code = _to_api_code(stock.get("code", ""))
            if not code:
                continue
            names[code] = stock.get("code_name") or code
        if names:
            logger.info(f"从 Baostock 全市场列表加载了 {len(names)} 只股票")
            return names
    except Exception as e:
        logger.warning(f"Baostock 全市场股票列表加载失败: {e}")
    return {}


def _load_stock_names_from_qlib_features() -> dict:
    features_dir = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "features"
    if not features_dir.exists():
        return {}

    names = {}
    for stock_dir in sorted(features_dir.iterdir()):
        if not stock_dir.is_dir():
            continue
        raw_code = stock_dir.name.upper()
        if not (
            raw_code.startswith("SH6")
            or raw_code.startswith("SZ0")
            or raw_code.startswith("SZ3")
            or raw_code.startswith("BJ4")
            or raw_code.startswith("BJ8")
            or raw_code.startswith("BJ920")
        ):
            continue
        api_code = _to_api_code(raw_code)
        names[api_code] = api_code
    if names:
        logger.info(f"从 Qlib 本地行情目录加载了 {len(names)} 只股票代码")
    return names


def _load_stock_names():
    """加载全市场股票名称映射（优先 Baostock，失败时用本地 Qlib 代码范围兜底）"""
    global _full_name_cache, _cache_loaded
    if _cache_loaded:
        return _full_name_cache

    _full_name_cache.update(_load_stock_names_from_provider())
    if not _full_name_cache:
        _full_name_cache.update(_load_stock_names_from_qlib_features())

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
    获取股票列表（全市场 A 股；无外部连接时返回本地 Qlib 已有代码范围）
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

    if not code_upper.startswith(("SH", "SZ", "BJ")):
        if code_upper.startswith("6") or code_upper.startswith("5"):
            code_upper = f"SH{code_upper}"
        elif code_upper.startswith(("4", "8")) or code_upper.startswith("920"):
            code_upper = f"BJ{code_upper}"
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
