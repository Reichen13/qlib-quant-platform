"""
首页仪表盘汇总 API
聚合板块、ETF、指数、策略信号供首页使用
"""

from datetime import date, datetime
from fastapi import APIRouter
from loguru import logger

router = APIRouter()


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
        from api.sectors import _get_all_stock_prices
        from core.sector_definitions import SECTOR_DEFINITIONS

        all_prices = _get_all_stock_prices()

        for sector_name, codes in SECTOR_DEFINITIONS.items():
            try:
                changes = []
                for code in codes:
                    info = all_prices.get(code)
                    if info:
                        changes.append(info["change_pct"])
                avg_chg = round(float(sum(changes) / len(changes)), 2) if changes else 0
                result["hot_sectors"].append({
                    "name": sector_name,
                    "change_pct": avg_chg,
                    "stock_count": len(codes),
                })
            except Exception:
                pass

        result["hot_sectors"].sort(key=lambda x: x["change_pct"], reverse=True)
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

    return result
