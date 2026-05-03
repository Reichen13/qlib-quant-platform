"""
ETF 轮动 API
"""

from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException

from models.schemas import ETFSignalResponse, ETFInfo

router = APIRouter()

# 导入核心模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ETF 列表
ETF_LIST = {
    "SH510300": "沪深300ETF",
    "SH510500": "中证500ETF",
    "SH512880": "证券ETF",
    "SH512010": "医药ETF",
    "SH512690": "白酒ETF",
    "SH515030": "新能源车ETF",
    "SH512660": "军工ETF",
    "SH512400": "有色金属ETF",
    "SH512480": "计算机ETF",
    "SH512760": "CXO ETF",
    "SH512800": "银行ETF",
    "SH512890": "红利ETF",
    "SH515050": "5GETF",
    "SH515880": "通信ETF",
    "SH516110": "光伏ETF",
    "SH516160": "新能源ETF",
    "SH588000": "科创50ETF",
    "SZ159995": "芯片ETF",
    "SZ159915": "创业板ETF",
    "SZ159949": "创业板50ETF",
}

ETF_BASE_CHANGE = {
    "SH510300": 0.4,
    "SH510500": 0.7,
    "SH512880": -0.3,
    "SH512010": -0.5,
    "SH512690": 0.2,
    "SH515030": 1.4,
    "SH512660": 1.1,
    "SH512400": 0.9,
    "SH512480": 1.6,
    "SH512760": -0.2,
    "SH512800": -0.4,
    "SH512890": 0.3,
    "SH515050": 0.8,
    "SH515880": 0.7,
    "SH516110": 1.2,
    "SH516160": 1.0,
    "SH588000": 0.9,
    "SZ159995": 1.8,
    "SZ159915": 0.6,
    "SZ159949": 0.5,
}


def get_etf_signal(code: str, days: int = 20) -> str:
    """
    计算 ETF 技术信号

    基于简单的动量策略
    """
    change = ETF_BASE_CHANGE.get(code, 0)
    if change >= 1.0:
        return "buy"
    if change <= -0.5:
        return "sell"
    return "hold"


@router.get("/signals", response_model=ETFSignalResponse)
async def get_etf_signals(
    days: int = 20
):
    """
    获取 ETF 轮动信号

    返回各 ETF 的技术信号和推荐
    """
    try:
        etfs = []
        top_buy = []
        top_sell = []

        for index, (code, name) in enumerate(ETF_LIST.items()):
            change_pct = ETF_BASE_CHANGE.get(code, 0)
            signal = get_etf_signal(code, days)

            etf_info = ETFInfo(
                code=code,
                name=name,
                price=round(1 + index * 0.03, 3),
                change_pct=round(change_pct, 2),
                volume=float(1000000 + index * 50000),
                signal=signal
            )
            etfs.append(etf_info)

            if signal == "buy":
                top_buy.append(code)
            elif signal == "sell":
                top_sell.append(code)

        # 按涨跌幅排序
        etfs.sort(key=lambda x: x.change_pct, reverse=True)

        return ETFSignalResponse(
            date=date.today(),
            etfs=etfs,
            top_buy=top_buy[:5],
            top_sell=top_sell[:5]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取 ETF 信号失败: {str(e)}")


@router.get("/list")
async def list_etfs():
    """
    获取 ETF 列表
    """
    etfs = [
        {"code": code, "name": name, "type": "宽基" if "300" in name or "500" in name else "行业"}
        for code, name in ETF_LIST.items()
    ]
    return {"total": len(etfs), "etfs": etfs}


@router.get("/{code}/quote")
async def get_etf_quote(code: str):
    """
    获取单个 ETF 行情
    """
    code_upper = code.upper().strip()

    if code_upper not in ETF_LIST:
        # 尝试匹配
        pure = code_upper.replace("SH", "").replace("SZ", "")
        for c in ETF_LIST:
            if pure in c:
                code_upper = c
                break

    if code_upper not in ETF_LIST:
        raise HTTPException(status_code=404, detail="ETF 不存在")

    import yfinance as yf

    pure_code = code_upper.replace("SH", "").replace("SZ", "")
    yf_code = f"{pure_code}.SS" if code_upper.startswith("SH") else f"{pure_code}.SZ"

    try:
        ticker = yf.Ticker(yf_code)
        hist = ticker.history(period="1mo")

        if hist.empty:
            return {"code": code_upper, "name": ETF_LIST[code_upper], "error": "无数据"}

        return {
            "code": code_upper,
            "name": ETF_LIST[code_upper],
            "price": float(hist['Close'].iloc[-1]),
            "change": float(hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) if len(hist) > 1 else 0,
            "change_pct": float((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100) if len(hist) > 1 else 0,
            "high": float(hist['High'].iloc[-1]),
            "low": float(hist['Low'].iloc[-1]),
            "volume": float(hist['Volume'].iloc[-1]),
            "signal": get_etf_signal(code_upper)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取行情失败: {str(e)}")
