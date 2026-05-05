"""
主题热点 API
"""

from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException, Query

from models.schemas import HotSectorsResponse, SectorInfo, SectorDetailResponse

router = APIRouter()

# 导入核心模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def get_calendar_range():
    """获取 Qlib 日历范围"""
    cal_path = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "calendars" / "day.txt"
    if not cal_path.exists():
        return None, None
    with open(cal_path) as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        return None, None
    return lines[0], lines[-1]


@router.get("/sectors", response_model=HotSectorsResponse)
async def get_hot_sectors(
    days: int = Query(default=10, ge=1, le=60, description="统计周期（天）")
):
    """
    获取热门板块涨跌幅排行

    基于指定周期内的板块涨跌幅进行排行
    """
    try:
        import qlib
        from qlib.data import D

        # 获取最新日期
        _, end_date_str = get_calendar_range()
        if not end_date_str:
            raise HTTPException(status_code=500, detail="无法获取日历数据")

        end_date = pd.to_datetime(end_date_str)
        start_date = end_date - timedelta(days=days + 20)  # 多取一些天数以确保有交易日

        from core.sector_definitions import get_sectors_qlib

        # 使用统一的板块定义（Qlib 格式）
        sectors = get_sectors_qlib()

        sector_results = []

        for sector_name, stock_codes in sectors.items():
            try:
                # 获取板块内股票的收盘价
                df = D.features(
                    stock_codes,
                    ["$close"],
                    start_time=start_date.strftime("%Y-%m-%d"),
                    end_time=end_date.strftime("%Y-%m-%d")
                )

                if df.empty:
                    continue

                # 计算板块涨跌幅
                # 获取期初期末价格
                first_prices = df.iloc[0]
                last_prices = df.iloc[-1]

                # 计算平均涨跌幅
                changes = []
                for code in stock_codes:
                    if (code, '$close') in first_prices.index and (code, '$close') in last_prices.index:
                        p1 = first_prices[(code, '$close')]
                        p2 = last_prices[(code, '$close')]
                        if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                            change = (p2 - p1) / p1
                            changes.append(change)

                if changes:
                    avg_change = np.mean(changes)
                    sector_results.append(SectorInfo(
                        name=sector_name,
                        change_pct=round(avg_change * 100, 2),
                        volume=len(changes),
                        stock_count=len(changes)
                    ))

            except Exception as e:
                # 跳过计算失败的板块
                continue

        # 按涨跌幅排序
        sector_results.sort(key=lambda x: x.change_pct, reverse=True)

        return HotSectorsResponse(
            date=end_date.date(),
            sectors=sector_results
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取板块数据失败: {str(e)}")


@router.get("/sector/{sector_name}/stocks")
async def get_sector_stocks(
    sector_name: str,
    days: int = Query(default=10, ge=1, le=60, description="统计周期（天）")
):
    """
    获取指定板块内的股票涨跌幅
    """
    try:
        from stock_names import get_stock_name, get_transparency_level
        import qlib
        from qlib.data import D
        from core.sector_definitions import get_sectors_qlib

        # 板块股票池（统一数据源）
        sector_stocks = get_sectors_qlib()

        if sector_name not in sector_stocks:
            raise HTTPException(status_code=404, detail=f"板块不存在: {sector_name}")

        stock_codes = sector_stocks[sector_name]

        # 获取最新日期
        _, end_date_str = get_calendar_range()
        if not end_date_str:
            raise HTTPException(status_code=500, detail="无法获取日历数据")

        end_date = pd.to_datetime(end_date_str)
        start_date = end_date - timedelta(days=days + 20)

        # 获取股票数据
        df = D.features(
            stock_codes,
            ["$close", "$volume"],
            start_time=start_date.strftime("%Y-%m-%d"),
            end_time=end_date.strftime("%Y-%m-%d")
        )

        if df.empty:
            return {"sector": sector_name, "stocks": []}

        # 计算涨跌幅
        results = []
        first_prices = df.iloc[0]
        last_prices = df.iloc[-1]

        from models.schemas import SectorStockInfo

        for code in stock_codes:
            if (code, '$close') in first_prices.index:
                p1 = first_prices[(code, '$close')]
                p2 = last_prices.get((code, '$close'), p1)
                vol = last_prices.get((code, '$volume'), 0)

                if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                    change_pct = (p2 - p1) / p1 * 100

                    results.append(SectorStockInfo(
                        code=code,
                        name=get_stock_name(code),
                        change_pct=round(change_pct, 2),
                        volume=float(vol) if pd.notna(vol) else 0,
                        factor_score=None  # TODO: 添加因子评分
                    ))

        # 按涨跌幅排序
        results.sort(key=lambda x: x.change_pct, reverse=True)

        return {
            "sector": sector_name,
            "stocks": results
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取板块股票失败: {str(e)}")
