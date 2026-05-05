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

        # 展平所有股票查询任务
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_quote(code):
            try:
                rs_quote = bs.query_history_k_data_plus(
                    code,
                    "date,code,pctChg",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",
                    adjustflag="2",
                )
                if rs_quote.error_code == '0':
                    changes = []
                    while (rs_quote.error_code == '0') & rs_quote.next():
                        pct = rs_quote.get_row_data()[2]
                        if pct:
                            changes.append(float(pct))
                    if changes:
                        return sum(changes) / len(changes)
            except Exception:
                pass
            return None

        # 展平为 (industry, code) 任务列表
        tasks = []
        for industry, codes in industry_stocks.items():
            for code in codes[:10]:
                tasks.append((industry, code))

        # 并行查询
        industry_changes: dict[str, list] = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_fetch_quote, code): (ind, code) for ind, code in tasks}
            for future in as_completed(futures):
                ind, code = futures[future]
                avg_change = future.result()
                if avg_change is not None:
                    if ind not in industry_changes:
                        industry_changes[ind] = []
                    industry_changes[ind].append(avg_change)

        # 汇总行业表现
        industry_performance = []
        for industry in industry_stocks:
            changes = industry_changes.get(industry, [])
            if changes:
                avg = sum(changes) / len(changes)
                industry_performance.append({
                    "industry": industry,
                    "change_pct": round(avg, 2),
                    "stock_count": len(changes),
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
