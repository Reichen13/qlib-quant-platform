"""
行业板块 API
基于 Baostock 提供行业分类和板块数据
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
        bs = provider._get_bs_client()
        if not bs:
            raise HTTPException(status_code=503, detail="数据源不可用")

        import baostock as bs
        rs = bs.query_stock_industry()

        industries = {}
        while (rs.error_code == '0') & rs.next():
            row = rs.get_row_data()
            industry_name = row[3]  # industry
            if industry_name:
                industries[industry_name] = industries.get(industry_name, 0) + 1

        # 转换为列表并排序
        industry_list = [
            {"name": k, "count": v}
            for k, v in sorted(industries.items(), key=lambda x: x[1], reverse=True)
        ]

        return {
            "total": len(industry_list),
            "industries": industry_list
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取行业列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stocks")
async def get_industry_stocks(
    industry: str = Query(..., description="行业名称")
):
    """
    获取指定行业的所有股票

    返回该行业下的所有股票列表
    """
    try:
        bs = provider._get_bs_client()
        if not bs:
            raise HTTPException(status_code=503, detail="数据源不可用")

        import baostock as bs
        rs = bs.query_stock_industry()

        stocks = []
        while (rs.error_code == '0') & rs.next():
            row = rs.get_row_data()
            if row[3] == industry:  # 行业匹配
                stocks.append({
                    "code": row[1],  # sh.600000
                    "name": row[2],  # 股票名称
                })

        return {
            "industry": industry,
            "count": len(stocks),
            "stocks": stocks
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
        from datetime import datetime, timedelta

        # 获取所有股票的行业
        bs = provider._get_bs_client()
        if not bs:
            raise HTTPException(status_code=503, detail="数据源不可用")

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")

        import baostock as bs
        rs_industry = bs.query_stock_industry()

        # 按行业分组
        industry_stocks = {}
        while (rs_industry.error_code == '0') & rs_industry.next():
            row = rs_industry.get_row_data()
            industry = row[3]
            if industry and industry not in industry_stocks:
                industry_stocks[industry] = []
            # 限制每个行业取前20只股票
            if industry and len(industry_stocks.get(industry, [])) < 20:
                industry_stocks[industry].append(row[1])

        # 计算行业平均涨跌幅
        industry_performance = []

        for industry, codes in industry_stocks.items():
            total_change = 0
            count = 0

            for code in codes[:10]:  # 每个行业取10只股票计算
                try:
                    rs_quote = bs.query_history_k_data_plus(
                        code,
                        "date,code,pctChg",
                        start_date=start_date,
                        end_date=end_date,
                        frequency="d",
                        adjustflag="2"
                    )

                    changes = []
                    while (rs_quote.error_code == '0') & rs_quote.next():
                        row = rs_quote.get_row_data()
                        if row[2]:  # pctChg
                            changes.append(float(row[2]))

                    if changes:
                        total_change += changes[-1] if changes else 0
                        count += 1
                except:
                    continue

            if count > 0:
                avg_change = total_change / count
                industry_performance.append({
                    "industry": industry,
                    "change_pct": round(avg_change, 2),
                    "stock_count": count
                })

        # 排序
        industry_performance.sort(key=lambda x: x["change_pct"], reverse=True)

        return {
            "date": end_date,
            "period_days": days,
            "sectors": industry_performance
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
