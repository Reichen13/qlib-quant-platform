"""
行业板块 API
基于 akshare 东方财富行业分类数据（原 Baostock 已替换）
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


@router.get("/stock/{code}")
async def get_stock_industry(code: str):
    """
    获取股票所属行业

    返回申万行业分类或证监会行业分类
    """
    try:
        industry = provider.get_industry(code)

        if industry is None:
            raise HTTPException(status_code=404, detail="无法获取行业信息")

        return industry

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取行业信息失败 {code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_industries():
    """
    获取所有行业分类列表

    返回可用的行业分类及其股票数量
    """
    try:
        import akshare as ak

        df = ak.stock_board_industry_name_em()
        industry_list = []
        for _, row in df.iterrows():
            name = str(row.get("板块名称") or "").strip()
            if not name:
                continue
            up = int(row.get("上涨家数") or 0)
            down = int(row.get("下跌家数") or 0)
            industry_list.append({
                "name": name,
                "count": up + down,
            })

        return {
            "total": len(industry_list),
            "industries": industry_list,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"获取行业列表失败，使用本地行业定义降级: {e}")
        from core.sector_definitions import SECTOR_DEFINITIONS

        fallback_industries = [
            {
                "name": name,
                "count": len(codes),
            }
            for name, codes in SECTOR_DEFINITIONS.items()
        ]
        return {
            "total": len(fallback_industries),
            "industries": fallback_industries,
            "data_status": "fallback",
            "source": "local_sector_definitions",
            "warning": "实时行业数据源暂不可用，已显示本地行业定义。",
        }


@router.get("/stocks")
async def get_industry_stocks(
    industry: str = Query(..., description="行业名称")
):
    """
    获取指定行业的所有股票

    返回该行业下的所有股票列表
    """
    try:
        import akshare as ak

        df = ak.stock_board_industry_cons_em(symbol=industry)
        stocks = []
        for _, row in df.iterrows():
            code = str(row.get("代码") or "").strip()
            name = str(row.get("名称") or "").strip()
            if code:
                stocks.append({"code": code, "name": name})

        return {
            "industry": industry,
            "count": len(stocks),
            "stocks": stocks,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取行业股票失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_industry_performance(
    days: int = Query(10, description="统计周期（天）")
):
    """
    获取各行业板块涨跌幅排行

    计算每个行业股票的平均涨跌幅
    """
    try:
        from datetime import datetime
        import akshare as ak

        end_date = datetime.now().strftime("%Y-%m-%d")

        df = ak.stock_board_industry_name_em()
        industry_performance = []
        for _, row in df.iterrows():
            name = str(row.get("板块名称") or "").strip()
            if not name:
                continue
            change_pct = row.get("涨跌幅")
            try:
                change_pct = round(float(change_pct), 2)
            except (TypeError, ValueError):
                change_pct = 0.0
            up = int(row.get("上涨家数") or 0)
            down = int(row.get("下跌家数") or 0)
            industry_performance.append({
                "industry": name,
                "change_pct": change_pct,
                "stock_count": up + down,
            })

        industry_performance.sort(key=lambda x: x["change_pct"], reverse=True)

        return {
            "date": end_date,
            "period_days": days,
            "sectors": industry_performance,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取行业表现失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rotation")
async def get_industry_rotation(
    top_n: int = Query(5, description="返回前N个行业")
):
    """
    获取行业轮动信号

    基于行业涨跌幅、资金流入等指标判断轮动机会
    """
    try:
        # 获取行业表现
        performance = await get_industry_performance(days=10)

        sectors = performance.get("sectors", [])

        # 计算轮动信号
        signals = []
        for i, sector in enumerate(sectors[:top_n]):
            change = sector["change_pct"]

            # 信号判断
            if change > 2:
                signal = "strong_buy"
                status = "强势"
            elif change > 1:
                signal = "buy"
                status = "流入"
            elif change > -1:
                signal = "hold"
                status = "观望"
            elif change > -2:
                signal = "avoid"
                status = "流出"
            else:
                signal = "sell"
                status = "弱势"

            signals.append({
                "rank": i + 1,
                "industry": sector["industry"],
                "change_pct": change,
                "signal": signal,
                "status": status
            })

        return {
            "date": performance.get("date"),
            "signals": signals
        }

    except Exception as e:
        logger.error(f"获取行业轮动失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
