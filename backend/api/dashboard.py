"""
首页仪表盘汇总 API
聚合板块、ETF、指数、策略信号供首页使用
"""

from datetime import date, datetime
from pathlib import Path
import json
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
        "etf_status": "ok",
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
        from api.etf import (
            _get_cached_history,
            _get_etf_universe,
            compute_signal,
            _local_etf_history_available,
            ETF_DATA_UNAVAILABLE_WARNING,
        )
        if not _local_etf_history_available():
            result["etf_status"] = "unavailable"
            result["etf_warning"] = ETF_DATA_UNAVAILABLE_WARNING
        else:
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


@router.get("/focus")
async def get_dashboard_focus():
    """
    持仓复核 + 今晚聚焦 3 只精选买入

    - 对已持仓股票: 对照当日收盘价与止损价输出 持有/止损触发/接近加仓
    - 从最新筛选 buyable 中取前 3 只附理由
    """
    holdings = []
    buyable_top3 = []

    # ── 持仓复核 ──
    try:
        from db.position_store import position_store
        from qlib.data import D
        import pandas as pd

        positions = position_store.list_all()
        if positions:
            codes = [p["code"] for p in positions]
            try:
                close_df = D.features(codes, ["$close"], start_time=None, end_time=None, freq="day")
            except Exception:
                close_df = None

            for pos in positions:
                code = pos["code"]
                name = pos["name"] or code
                cost = pos["cost_price"]
                stop_loss = pos.get("stop_loss_price")
                shares = pos["shares"]
                current_price = None
                current_change_pct = None

                if close_df is not None and code in close_df.columns.get_level_values("instrument"):
                    try:
                        series = close_df.xs(code, level="instrument")["$close"].dropna()
                        if not series.empty:
                            current_price = round(float(series.iloc[-1]), 2)
                            if len(series) >= 2:
                                prev = float(series.iloc[-2])
                                if prev > 0:
                                    current_change_pct = round((current_price - prev) / prev * 100, 2)
                    except Exception:
                        pass

                # 判定
                if current_price is None:
                    verdict = "待更新"
                    verdict_reason = "无法获取最新价"
                elif stop_loss is not None and current_price <= stop_loss:
                    verdict = "止损触发"
                    verdict_reason = f"当前价 {current_price} <= 止损价 {stop_loss}"
                elif current_price < cost * 0.92:
                    verdict = "深度亏损"
                    verdict_reason = f"当前价 {current_price} 低于成本 {cost} 8%以上"
                elif current_price < cost * 0.97:
                    verdict = "浮亏观察"
                    verdict_reason = f"当前价 {current_price} 低于成本 {cost} 3%以上"
                elif current_price < cost:
                    verdict = "微亏持有"
                    verdict_reason = f"当前价 {current_price} < 成本 {cost}"
                elif current_price > cost * 1.10:
                    verdict = "浮盈持有"
                    verdict_reason = f"当前价 {current_price} > 成本 {cost} 10%以上"
                else:
                    verdict = "持有"
                    verdict_reason = "价格在成本附近"

                holdings.append({
                    "code": code,
                    "name": name,
                    "shares": shares,
                    "cost_price": cost,
                    "stop_loss_price": stop_loss,
                    "current_price": current_price,
                    "change_pct": current_change_pct,
                    "pnl_pct": round((current_price - cost) / cost * 100, 2) if current_price else None,
                    "verdict": verdict,
                    "verdict_reason": verdict_reason,
                })
    except Exception as e:
        logger.warning(f"持仓复核失败: {e}")
        holdings = []

    # ── 精选前 3 只买入 ──
    try:
        from db.task_store import TaskStore
        screening_store = TaskStore(
            Path.home() / ".qlib" / "screening_tasks.db",
            table_name="screening_tasks"
        )
        screening_store.init_db()
        tasks = screening_store.list_tasks(limit=5)
        for t in tasks:
            if t.get("status") == "completed" and t.get("result_json"):
                try:
                    result = json.loads(t["result_json"])
                    candidates = result.get("candidates", [])
                    buyable = [c for c in candidates if c.get("bucket") == "buyable"]
                    buyable.sort(key=lambda x: x.get("score", 0), reverse=True)
                    buyable_top3 = buyable[:3]
                    break
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"获取精选买入失败: {e}")
        buyable_top3 = []

    return {
        "date": date.today().isoformat(),
        "holdings": holdings,
        "buyable_top3": buyable_top3,
        "holdings_count": len(holdings),
        "updated_at": datetime.now().isoformat(),
    }
