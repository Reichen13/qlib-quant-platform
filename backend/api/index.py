"""
指数成分股 API
提供沪深300、上证50、中证500等指数成分股数据
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from datetime import datetime

router = APIRouter()

# 导入数据提供者
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.data_provider import get_provider

provider = get_provider()


def _summarize_index_data(data):
    closes = [d["close"] for d in data if d["close"] is not None]
    changes = [d["change_pct"] for d in data if d["change_pct"] is not None]

    total_return = (closes[-1] - closes[0]) / closes[0] * 100 if len(closes) >= 2 and closes[0] else 0
    avg_change = sum(changes) / len(changes) if changes else 0
    max_drawdown = 0
    peak = closes[0] if closes else 0

    for close in closes:
        if close > peak:
            peak = close
        if peak:
            drawdown = (close - peak) / peak * 100
            if drawdown < max_drawdown:
                max_drawdown = drawdown

    return {
        "total_return": round(total_return, 2),
        "avg_daily_change": round(avg_change, 2),
        "max_drawdown": round(max_drawdown, 2),
        "current_price": closes[-1] if closes else None,
    }


def _fallback_index_performance(index: str, days: int):
    base_values = {"hs300": 3600.0, "sz50": 2500.0, "zz500": 5400.0}
    base = base_values.get(index, 3600.0)
    data = []
    start = datetime.now() - __import__("datetime").timedelta(days=days)

    for i in range(days):
        value = base + i * 1.8 + ((i % 7) - 3) * 6
        prev = base + (i - 1) * 1.8 + (((i - 1) % 7) - 3) * 6 if i > 0 else value
        change_pct = ((value - prev) / prev * 100) if prev else 0
        data.append({
            "date": (start + __import__("datetime").timedelta(days=i + 1)).strftime("%Y-%m-%d"),
            "open": round(value * 0.998, 2),
            "high": round(value * 1.006, 2),
            "low": round(value * 0.994, 2),
            "close": round(value, 2),
            "change_pct": round(change_pct, 2),
        })

    return {
        "index": index,
        "period_days": days,
        "data": data,
        "summary": _summarize_index_data(data),
        "source": "fallback",
        "warning": "synthetic_fallback — 无 Qlib/baostock 数据，使用合成数据",
    }


def _qlib_index_performance(index: str, days: int):
    index_codes = {
        "hs300": "SH000300",
        "sz50": "SH000016",
        "zz500": "SH000905",
    }
    code = index_codes.get(index)
    if not code:
        return None

    try:
        from datetime import timedelta
        from qlib.data import D

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days * 3)
        df = D.features(
            [code],
            ["$open", "$high", "$low", "$close"],
            start_time=start_date.strftime("%Y-%m-%d"),
            end_time=end_date.strftime("%Y-%m-%d"),
        )
        if df.empty:
            return None

        data = []
        prev_close = None
        for idx, row in df.tail(days).iterrows():
            date_val = idx[1] if isinstance(idx, tuple) else idx
            close = float(row["$close"]) if row["$close"] == row["$close"] else None
            change_pct = None
            if close is not None and prev_close:
                change_pct = (close - prev_close) / prev_close * 100
            if close is not None:
                prev_close = close

            data.append({
                "date": date_val.strftime("%Y-%m-%d"),
                "open": float(row["$open"]) if row["$open"] == row["$open"] else None,
                "high": float(row["$high"]) if row["$high"] == row["$high"] else None,
                "low": float(row["$low"]) if row["$low"] == row["$low"] else None,
                "close": close,
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
            })

        if not data:
            return None

        return {
            "index": index,
            "period_days": days,
            "data": data,
            "summary": _summarize_index_data(data),
            "source": "qlib",
        }
    except Exception as e:
        logger.debug(f"Qlib 指数表现不可用 {index}: {e}")
        return None


@router.get("/stocks")
async def get_index_stocks(
    index: str = Query("hs300", description="指数代码: hs300, sz50, zz500"),
    date: str = Query(None, description="查询日期，格式 YYYY-MM-DD，为空时取最新")
):
    """
    获取指数成分股列表

    支持的指数：
    - hs300: 沪深300
    - sz50: 上证50
    - zz500: 中证500
    """
    try:
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        stocks = provider.get_index_stocks(index)

        if not stocks:
            raise HTTPException(status_code=404, detail=f"无法获取 {index} 成分股")

        return {
            "index": index,
            "date": date,
            "count": len(stocks),
            "stocks": stocks
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取指数成分股失败 {index}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_indices():
    """
    获取支持的指数列表
    """
    return {
        "indices": [
            {
                "code": "hs300",
                "name": "沪深300",
                "description": "由上海和深圳证券市场中市值大、流动性好的300只股票组成",
                "count": 300
            },
            {
                "code": "sz50",
                "name": "上证50",
                "description": "由上海证券市场规模大、流动性好的最具代表性的50只股票组成",
                "count": 50
            },
            {
                "code": "zz500",
                "name": "中证500",
                "description": "由全部A股中剔除沪深300指数成份股后，总市值排名前500的股票组成",
                "count": 500
            }
        ]
    }


@router.get("/performance")
async def get_index_performance(
    index: str = Query("hs300", description="指数代码"),
    days: int = Query(30, description="统计周期（天）")
):
    """
    获取指数表现数据

    返回指数在指定周期内的涨跌幅、波动率等
    """
    if index not in {"hs300", "sz50", "zz500"}:
        raise HTTPException(status_code=400, detail=f"不支持的指数: {index}")

    qlib_result = _qlib_index_performance(index, days)
    if qlib_result:
        return qlib_result

    try:
        from datetime import timedelta

        bs = provider._get_bs_client()
        if not bs:
            return _fallback_index_performance(index, days)

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")

        # 指数代码映射
        index_codes = {
            "hs300": "sh.000300",
            "sz50": "sh.000016",
            "zz500": "sh.000905"
        }

        code = index_codes.get(index)
        if not code:
            raise HTTPException(status_code=400, detail=f"不支持的指数: {index}")

        import baostock as bs
        rs = bs.query_history_k_data_plus(
            code,
            "date,code,open,high,low,close,pctChg",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3"  # 不复权
        )

        if rs.error_code != '0':
            return _fallback_index_performance(index, days)

        data = []
        while (rs.error_code == '0') & rs.next():
            row = rs.get_row_data()
            data.append({
                "date": row[0],
                "open": float(row[2]) if row[2] else None,
                "high": float(row[3]) if row[3] else None,
                "low": float(row[4]) if row[4] else None,
                "close": float(row[5]) if row[5] else None,
                "change_pct": float(row[6]) if row[6] else None,
            })

        if not data:
            return _fallback_index_performance(index, days)

        data = data[-days:]
        return {
            "index": index,
            "period_days": days,
            "data": data,
            "summary": _summarize_index_data(data),
            "source": "baostock",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取指数表现失败 {index}: {e}")
        return _fallback_index_performance(index, days)


@router.get("/comparison")
async def compare_indices():
    """
    对比主要指数表现

    返回沪深300、上证50、中证500的对比数据
    """
    try:
        indices = ["hs300", "sz50", "zz500"]
        results = []

        for idx in indices:
            try:
                perf = await get_index_performance(index=idx, days=30)
                results.append({
                    "code": idx,
                    "total_return": perf["summary"]["total_return"],
                    "avg_daily_change": perf["summary"]["avg_daily_change"],
                    "max_drawdown": perf["summary"]["max_drawdown"],
                    "current_price": perf["summary"]["current_price"],
                })
            except:
                continue

        # 按收益率排序
        results.sort(key=lambda x: x["total_return"], reverse=True)

        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "comparison": results
        }

    except Exception as e:
        logger.error(f"对比指数失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
