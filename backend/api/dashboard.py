"""
首页仪表盘汇总 API
聚合板块、ETF、指数、策略信号供首页使用
"""

from datetime import date, datetime
from fastapi import APIRouter
from loguru import logger

router = APIRouter()


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


@router.get("/summary")
async def get_dashboard_summary():
    """
    首页仪表盘数据汇总

    聚合热门板块、ETF 信号、指数对比等数据
    """
    result = {
        "date": date.today().isoformat(),
        "hot_sectors": [],
        "etf_signals": [],
        "index_comparison": [],
        "strategy_signals": [],
        "updated_at": datetime.now().isoformat(),
    }

    # ── 热门板块 ──
    try:
        from api.hot import get_hot_sectors

        hot_response = await get_hot_sectors(days=10)
        for sector in getattr(hot_response, "sectors", []):
            sector_data = sector.model_dump() if hasattr(sector, "model_dump") else {
                "name": getattr(sector, "name", ""),
                "change_pct": getattr(sector, "change_pct", 0),
                "stock_count": getattr(sector, "stock_count", 0),
            }
            result["hot_sectors"].append({
                "name": sector_data.get("name"),
                "change_pct": float(sector_data.get("change_pct") or 0),
                "stock_count": int(sector_data.get("stock_count") or 0),
            })
    except Exception as e:
        logger.warning(f"Dashboard 板块数据获取失败: {e}")

    # ── ETF 信号 ──
    try:
        from api.etf import _get_cached_history, _get_etf_universe, compute_signal
        all_history = _get_cached_history()
        for code, name in list(_get_etf_universe().items())[:6]:
            hist = all_history.get(code)
            if hist is not None and len(hist) >= 10 and "Close" in hist:
                prices = hist["Close"].dropna()
                signal, chg, _ = compute_signal(prices)
                result["etf_signals"].append({
                    "name": name,
                    "code": code,
                    "change_pct": chg,
                    "signal": signal,
                })
    except Exception as e:
        logger.warning(f"Dashboard ETF 数据获取失败: {e}")

    # ── 策略信号摘要 ──
    if result["hot_sectors"]:
        top = result["hot_sectors"][0]
        up_count = sum(1 for s in result["hot_sectors"] if s["change_pct"] > 0)
        down_count = sum(1 for s in result["hot_sectors"] if s["change_pct"] < 0)

        if up_count > down_count * 2:
            market_bias = "偏多"
        elif down_count > up_count * 2:
            market_bias = "偏空"
        else:
            market_bias = "震荡"

        result["strategy_signals"] = [
            {
                "strategy": "因子策略",
                "signal": "买入" if up_count >= 4 else "关注",
                "reason": f"Top板块「{top['name']}」涨幅 {top['change_pct']:+.1f}%，{up_count}个板块上涨",
                "data_status": "derived",
                "source": "sector_proxy",
            },
            {
                "strategy": "ETF 轮动",
                "signal": "增持" if market_bias == "偏多" else ("持有" if market_bias == "震荡" else "减仓"),
                "reason": f"市场情绪{market_bias}，{up_count}/{up_count + down_count}板块上涨",
                "data_status": "derived",
                "source": "sector_proxy",
            },
        ]

    return _json_safe(result)
