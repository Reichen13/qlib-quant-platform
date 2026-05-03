"""
行情数据 API
"""

from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List, Optional
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException, Query

from models.schemas import QuoteResponse, QuoteData, IndicatorData

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


@router.get("/{code}", response_model=QuoteResponse)
async def get_quote(
    code: str,
    start_date: Optional[str] = Query(default=None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(default=None, description="结束日期 YYYY-MM-DD"),
    indicators: bool = Query(default=True, description="是否计算技术指标")
):
    """
    获取股票行情数据（K线）

    返回指定时间范围内的开高低收成交量数据
    """
    try:
        from stock_names import get_stock_name
        import qlib
        from qlib.data import D

        # 规范化代码
        code_upper = code.upper().strip()
        if not code_upper.startswith(("SH", "SZ")):
            if code_upper.startswith("6") or code_upper.startswith("5"):
                code_upper = f"SH{code_upper}"
            else:
                code_upper = f"SZ{code_upper}"

        # 确定日期范围
        _, latest_date_str = get_calendar_range()
        if not latest_date_str:
            raise HTTPException(status_code=500, detail="无法获取日历数据")

        if end_date:
            end_dt = pd.to_datetime(end_date)
        else:
            end_dt = pd.to_datetime(latest_date_str)

        if start_date:
            start_dt = pd.to_datetime(start_date)
        else:
            # 默认返回近3个月数据
            start_dt = end_dt - timedelta(days=90)

        # 获取行情数据
        df = D.features(
            [code_upper],
            ["$open", "$high", "$low", "$close", "$volume", "$money"],
            start_time=start_dt.strftime("%Y-%m-%d"),
            end_time=end_dt.strftime("%Y-%m-%d")
        )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"无法获取股票 {code_upper} 的数据")

        # 构建返回数据
        quote_data = []
        for idx, row in df.iterrows():
            # Qlib 返回的 MultiIndex 格式是 (instrument, datetime)
            date_val = idx[1] if isinstance(idx, tuple) else idx
            # Qlib 返回的列是单层索引，直接用列名访问
            quote_data.append(QuoteData(
                date=pd.to_datetime(date_val).date(),
                open=float(row["$open"]) if pd.notna(row["$open"]) else 0,
                high=float(row["$high"]) if pd.notna(row["$high"]) else 0,
                low=float(row["$low"]) if pd.notna(row["$low"]) else 0,
                close=float(row["$close"]) if pd.notna(row["$close"]) else 0,
                volume=float(row["$volume"]) if pd.notna(row["$volume"]) else 0,
                amount=float(row["$money"]) if pd.notna(row["$money"]) else None,
            ))

        # 计算技术指标
        indicator_data = []
        if indicators and len(quote_data) >= 20:
            closes = [d.close for d in quote_data]
            dates = [d.date for d in quote_data]

            # 计算移动平均线
            for i in range(len(quote_data)):
                ind = IndicatorData(date=dates[i])

                # MA
                if i >= 4:
                    ind.ma5 = round(sum(closes[i-4:i+1]) / 5, 2)
                if i >= 9:
                    ind.ma10 = round(sum(closes[i-9:i+1]) / 10, 2)
                if i >= 19:
                    ind.ma20 = round(sum(closes[i-19:i+1]) / 20, 2)
                if i >= 59:
                    ind.ma60 = round(sum(closes[i-59:i+1]) / 60, 2)

                # RSI (14)
                if i >= 14:
                    gains = []
                    losses = []
                    for j in range(i-13, i+1):
                        diff = closes[j] - closes[j-1]
                        if diff > 0:
                            gains.append(diff)
                            losses.append(0)
                        else:
                            gains.append(0)
                            losses.append(-diff)

                    avg_gain = sum(gains) / 14
                    avg_loss = sum(losses) / 14

                    if avg_loss == 0:
                        ind.rsi = 100
                    else:
                        rs = avg_gain / avg_loss
                        ind.rsi = round(100 - (100 / (1 + rs)), 2)

                indicator_data.append(ind)

        return QuoteResponse(
            code=code_upper,
            name=get_stock_name(code_upper),
            data=quote_data,
            indicators=indicator_data if indicators else None
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取行情数据失败: {str(e)}")


@router.get("/{code}/info")
async def get_stock_info_quote(code: str):
    """
    获取股票基本信息（用于行情页）
    """
    try:
        from stock_names import get_stock_name, get_transparency_level
        import yfinance as yf

        # 规范化代码
        code_upper = code.upper().strip()
        if not code_upper.startswith(("SH", "SZ")):
            if code_upper.startswith("6") or code_upper.startswith("5"):
                code_upper = f"SH{code_upper}"
            else:
                code_upper = f"SZ{code_upper}"

        # 转换为 yfinance 格式
        pure_code = code_upper.replace("SH", "").replace("SZ", "")
        if pure_code.startswith("6") or pure_code.startswith("5"):
            yf_code = f"{pure_code}.SS"
        else:
            yf_code = f"{pure_code}.SZ"

        # 获取实时数据
        ticker = yf.Ticker(yf_code)
        info = ticker.info

        return {
            "code": code_upper,
            "name": get_stock_name(code_upper),
            "market": "SH" if code_upper.startswith("SH") else "SZ",
            "transparency": get_transparency_level(code_upper),
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "change": info.get("previousClose") and info.get("currentPrice") and
                     round(info.get("currentPrice") - info.get("previousClose"), 2),
            "change_percent": info.get("previousClose") and info.get("currentPrice") and
                            round(((info.get("currentPrice") - info.get("previousClose")) /
                                  info.get("previousClose")) * 100, 2),
            "high_52w": info.get("fiftyTwoWeekHigh"),
            "low_52w": info.get("fiftyTwoWeekLow"),
            "market_cap": info.get("marketCap"),
            "volume": info.get("volume"),
        }

    except Exception as e:
        # 返回基本信息
        from stock_names import get_stock_name, get_transparency_level
        code_upper = code.upper().strip()
        if not code_upper.startswith(("SH", "SZ")):
            if code_upper.startswith("6") or code_upper.startswith("5"):
                code_upper = f"SH{code_upper}"
            else:
                code_upper = f"SZ{code_upper}"

        return {
            "code": code_upper,
            "name": get_stock_name(code_upper),
            "market": "SH" if code_upper.startswith("SH") else "SZ",
            "transparency": get_transparency_level(code_upper),
            "price": None,
            "change": None,
            "change_percent": None,
            "error": str(e)
        }
