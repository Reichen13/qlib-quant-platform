"""
首页仪表盘汇总 API
聚合板块、ETF、指数、策略信号供首页使用
"""

from datetime import date, datetime
from pathlib import Path
import json

import pandas as pd
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


def _code_to_feature_dir(code: str) -> str:
    """Normalize stock code to qlib feature folder name like sh600519."""
    c = str(code or "").strip()
    try:
        from utils.code_normalization import normalize_stock_code
        return normalize_stock_code(c, target="qlib").lower()
    except Exception:
        low = c.lower().replace(".ss", "").replace(".sz", "").replace(".bj", "")
        if low.startswith(("sh", "sz", "bj")):
            return low
        if low.isdigit() and len(low) == 6:
            if low.startswith(("5", "6", "9")):
                return "sh" + low
            return "sz" + low
        return low


def _last_two_closes_from_bin(code: str) -> tuple[float | None, float | None]:
    """Read last two valid closes from local bin — no Qlib D.features (avoids joblib hang)."""
    import numpy as np

    path = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "features" / _code_to_feature_dir(code) / "close.day.bin"
    if not path.exists():
        return None, None
    try:
        raw = np.fromfile(str(path), dtype="<f")
        if len(raw) < 3:
            return None, None
        vals = raw[1:]
        vi = np.where(np.isfinite(vals) & (vals > 0))[0]
        if len(vi) == 0:
            return None, None
        last = float(vals[int(vi[-1])])
        prev = float(vals[int(vi[-2])]) if len(vi) >= 2 else None
        return last, prev
    except Exception:
        return None, None


@router.get("/focus")
async def get_dashboard_focus():
    """
    持仓复核 + 今晚聚焦 3 只精选买入（必须轻量，供首页 8–30s 内返回）

    - 可买 Top3：SQLite screening_history（无重计算）
    - 持仓价：本地 close.day.bin 末两根（禁止 D.features 全历史）
    - data_trust：优先缓存，冷启动用小样本
    """
    holdings = []
    buyable_top3 = []
    buyable_source = None

    # 1) 可买精选 — 纯 SQLite，应 <50ms
    try:
        from db.screening_history import get_latest_buyable, get_recent_runs

        history_items = get_latest_buyable(limit=3)
        if history_items:
            buyable_top3 = history_items
            runs = get_recent_runs(limit=1)
            buyable_source = {
                "source": "screening_history",
                "run_date": runs[0]["run_date"] if runs else None,
            }
    except Exception as e:
        logger.warning(f"focus screening_history failed: {e}")

    if not buyable_top3:
        try:
            from db.task_store import TaskStore
            screening_store = TaskStore(
                Path.home() / ".qlib" / "screening_run_tasks.db",
                table_name="screening_run_tasks",
            )
            screening_store.init_db()
            tasks = screening_store.list_tasks(limit=5)
            for t in tasks:
                if t.get("status") == "completed" and t.get("result_json"):
                    try:
                        result = json.loads(t["result_json"])
                        buyable = [
                            c for c in (result.get("candidates") or [])
                            if c.get("bucket") == "buyable"
                        ]
                        if not buyable:
                            buyable = list((result.get("buckets") or {}).get("buyable") or [])
                        buyable.sort(key=lambda x: x.get("score", 0) or 0, reverse=True)
                        if not buyable:
                            continue
                        buyable_top3 = buyable[:3]
                        buyable_source = {"source": "screening_task", "task_id": t.get("task_id")}
                        break
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"获取精选买入失败: {e}")

    # 2) 持仓复核 — 本地 bin 末价，禁止 Qlib Dataset
    try:
        from db.position_store import position_store
        from core.price_adjust import to_forward_price

        positions = position_store.list_all()
        for pos in positions:
            code = pos["code"]
            name = pos["name"] or code
            cost = pos["cost_price"]
            stop_loss = pos.get("stop_loss_price")
            shares = pos["shares"]
            current_price = None
            current_change_pct = None

            raw_last, raw_prev = _last_two_closes_from_bin(code)
            if raw_last is not None:
                try:
                    current_price = round(to_forward_price(raw_last, code), 2)
                    if raw_prev is not None and raw_prev > 0:
                        prev = to_forward_price(raw_prev, code)
                        if prev > 0:
                            current_change_pct = round((current_price - prev) / prev * 100, 2)
                except Exception:
                    current_price = round(float(raw_last), 2)

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

    # 3) data_trust：缓存优先；冷启动小样本，避免扫 400 只拖死首页
    trading_allowed = True
    data_trust = None
    try:
        from core.data_trust import evaluate_data_trust

        data_trust = evaluate_data_trust(max_sample=80, use_cache=True)
        trading_allowed = bool(data_trust.get("trading_allowed"))
        if not trading_allowed:
            buyable_top3 = []
    except Exception as e:
        logger.warning(f"focus data_trust failed: {e}")

    # 4) 熔断：只读库内已验证胜率，不重算 Qlib
    circuit_breaker = {"active": False, "message": None}
    try:
        from db.screening_history import get_last_n_runs

        aged = get_last_n_runs(n=3, min_age_days=5)
        verified_wrs = [
            r["win_rate_verified"]
            for r in aged
            if r.get("win_rate_verified") is not None
        ]
        if len(verified_wrs) >= 3 and all(float(w) < 0.40 for w in verified_wrs[:3]):
            circuit_breaker = {
                "active": True,
                "message": "近3期筛选 T+5 胜率均低于40%，建议暂停新开仓",
                "recent_win_rates": verified_wrs[:3],
            }
            buyable_top3 = []
            trading_allowed = False
    except Exception as e:
        logger.warning(f"focus circuit_breaker failed: {e}")

    # 5) DL 深度学习信号 — 只读已完成预测，不触发计算
    dl_signals = []
    try:
        from core.dl_models import get_available_models, get_latest_prediction

        models = get_available_models()
        for m in models:
            if not m.get("is_trained"):
                continue
            pred = get_latest_prediction(m["id"])
            if not pred or "predictions" not in pred:
                continue
            for item in pred["predictions"][:5]:
                dl_signals.append({
                    "code": item.get("code"),
                    "name": item.get("name"),
                    "score": item.get("score"),
                    "model": m["id"],
                    "model_name": m["full_name"],
                    "pred_date": pred.get("pred_date", ""),
                })
        dl_signals.sort(key=lambda x: x.get("score", 0), reverse=True)
        dl_signals = dl_signals[:10]
    except Exception as e:
        logger.warning(f"focus dl_signals failed: {e}")

    return {
        "date": date.today().isoformat(),
        "holdings": holdings,
        "buyable_top3": buyable_top3,
        "buyable_source": buyable_source,
        "holdings_count": len(holdings),
        "trading_allowed": trading_allowed,
        "circuit_breaker": circuit_breaker,
        "dl_signals": dl_signals,
        "data_trust": {
            "trusted": data_trust.get("trusted") if data_trust else None,
            "status": data_trust.get("status") if data_trust else None,
            "message": data_trust.get("message") if data_trust else None,
            "metrics": data_trust.get("metrics") if data_trust else None,
        },
        "updated_at": datetime.now().isoformat(),
    }
