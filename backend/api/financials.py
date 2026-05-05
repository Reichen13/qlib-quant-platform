"""
财务数据 API
基于 Baostock 提供完整的财务指标数据
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from loguru import logger

router = APIRouter()

# 导入数据提供者
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.data_provider import get_provider

provider = get_provider()


@router.get("/summary/{code}")
async def get_financial_summary(code: str):
    """
    获取股票财务数据汇总

    包含：盈利能力、成长能力、营运能力、杜邦指数
    """
    try:
        summary = provider.get_financial_summary(code)

        if summary is None:
            raise HTTPException(status_code=404, detail="无法获取财务数据")

        return summary

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取财务汇总失败 {code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profit/{code}")
async def get_profit_data(
    code: str,
    year: int = Query(..., description="年份，如 2023"),
    quarter: int = Query(..., description="季度: 1,2,3,4")
):
    """
    获取盈利能力数据

    包含：ROE、销售净利率、销售毛利率、净利润、EPS等
    """
    try:
        data = provider.get_profit_data(code, year, quarter)

        if data is None:
            raise HTTPException(status_code=404, detail="无法获取盈利数据")

        return data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取盈利数据失败 {code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/growth/{code}")
async def get_growth_data(
    code: str,
    year: int = Query(..., description="年份"),
    quarter: int = Query(..., description="季度")
):
    """
    获取成长能力数据

    包含：净利润同比增长率、EPS同比增长率、归母净利润同比增长率
    """
    try:
        data = provider.get_growth_data(code, year, quarter)

        if data is None:
            raise HTTPException(status_code=404, detail="无法获取成长数据")

        return data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取成长数据失败 {code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/operation/{code}")
async def get_operation_data(
    code: str,
    year: int = Query(..., description="年份"),
    quarter: int = Query(..., description="季度")
):
    """
    获取营运能力数据

    包含：应收账款周转率、存货周转率、总资产周转率
    """
    try:
        data = provider.get_operation_data(code, year, quarter)

        if data is None:
            raise HTTPException(status_code=404, detail="无法获取营运数据")

        return data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取营运数据失败 {code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dupont/{code}")
async def get_dupont_data(
    code: str,
    year: int = Query(..., description="年份"),
    quarter: int = Query(..., description="季度")
):
    """
    获取杜邦指数数据

    ROE 分解：权益乘数、总资产周转率、净利润率
    """
    try:
        data = provider.get_dupont_data(code, year, quarter)

        if data is None:
            raise HTTPException(status_code=404, detail="无法获取杜邦数据")

        return data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取杜邦数据失败 {code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rank")
async def get_financial_rank(
    metric: str = Query("roe", description="排序指标: roe, npMargin, YOYNI"),
    order: str = Query("desc", description="排序方向: desc, asc"),
    limit: int = Query(50, description="返回数量")
):
    """
    获取财务指标排行榜

    根据 ROE、净利润增长率等指标对股票进行排序
    """
    try:
        # 获取沪深300成分股
        stocks = provider.get_index_stocks("hs300")

        if not stocks:
            raise HTTPException(status_code=404, detail="无法获取股票列表")

        results = []

        # 获取最近季度
        from datetime import datetime
        from concurrent.futures import ThreadPoolExecutor, as_completed
        today = datetime.now()
        year = today.year
        quarter = (today.month - 1) // 3 + 1
        if quarter > 4:
            quarter = 4

        # 并行查询（最多 8 线程，单查询 5s 超时）
        def _fetch_one(stock):
            code = provider._from_baostock_code(stock["code"])
            try:
                if metric == "roe" or metric == "npMargin":
                    data = provider.get_profit_data(code, year, quarter)
                elif metric == "YOYNI" or metric == "YOYEPSBasic":
                    data = provider.get_growth_data(code, year, quarter)
                elif metric == "AssetTurnRatio":
                    data = provider.get_operation_data(code, year, quarter)
                else:
                    data = provider.get_profit_data(code, year, quarter)

                if data and data.get(metric) is not None:
                    return {
                        "code": code,
                        "name": stock["name"],
                        "value": data[metric],
                        "year": year,
                        "quarter": quarter,
                    }
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(_fetch_one, s): s for s in stocks[:100]}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        # 排序
        reverse = order == "desc"
        results.sort(key=lambda x: x["value"], reverse=reverse)

        return {
            "metric": metric,
            "order": order,
            "total": len(results),
            "rankings": results[:limit]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取财务排行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
