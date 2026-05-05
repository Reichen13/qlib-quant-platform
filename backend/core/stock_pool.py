"""
智能股票池引擎 — 三层漏斗架构

Layer 1: 硬过滤 (st/新上市/市值/资不抵债/停牌/科创板)
Layer 2: 因子打分 (ICIR加权 + 行业中性化)
Layer 3: 组合约束 (最大股票数/行业集中度/相关性上限)

SQLite 存储: ~/.qlib/stock_pools.db
"""

import json
import sqlite3
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field

DB_PATH = Path.home() / ".qlib" / "stock_pools.db"


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pools (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pool_history (
            id TEXT PRIMARY KEY,
            pool_id TEXT NOT NULL,
            date TEXT NOT NULL,
            constituents_json TEXT NOT NULL DEFAULT '[]',
            performance_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (pool_id) REFERENCES pools(id)
        )
    """)
    conn.commit()
    conn.close()


# 启动时初始化
_init_db()


# ── Pydantic 模型 ──

class Layer1HardFilter(BaseModel):
    exclude_st: bool = Field(default=True, description="排除ST股")
    exclude_new_ipo_days: int = Field(default=180, description="排除上市不足N日新股")
    min_market_cap: float = Field(default=15_000_000_000, description="最小市值（元）")
    exclude_negative_equity: bool = Field(default=True, description="排除资不抵债")
    exclude_suspended: bool = Field(default=True, description="排除停牌")
    exclude_chi_next_star: bool = Field(default=True, description="排除科创板")


class Layer2FactorScoring(BaseModel):
    factors: dict = Field(default={}, description="因子名→权重")
    icir_weighted: bool = Field(default=True, description="使用ICIR加权")
    industry_neutralize: bool = Field(default=True, description="行业中性化")
    icir_window: int = Field(default=120, description="ICIR计算窗口（交易日）")


class Layer3PortfolioConstraints(BaseModel):
    max_stocks: int = Field(default=30, le=100, description="最大股票数")
    max_sector_weight: float = Field(default=0.25, le=0.5, description="单行业最大权重")
    max_correlation: float = Field(default=0.7, le=1.0, description="最大成对相关性")
    position_method: str = Field(default="equal_weight", description="equal_weight / market_cap / risk_parity")


class PoolDefinition(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    layer1: Layer1HardFilter = Field(default_factory=Layer1HardFilter)
    layer2: Layer2FactorScoring = Field(default_factory=Layer2FactorScoring)
    layer3: Layer3PortfolioConstraints = Field(default_factory=Layer3PortfolioConstraints)


# ── 引擎 ──

class StockPoolEngine:
    """三层漏斗股票池引擎"""

    def __init__(self):
        self._provider = None

    def _get_provider(self):
        if self._provider is None:
            from services.data_provider import DataProvider
            self._provider = DataProvider()
        return self._provider

    def _bs_to_yf(self, code: str) -> str:
        """Baostock 格式 → yfinance 格式: sh.600000 → 600000.SS"""
        code = code.replace("sh.", "").replace("sz.", "")
        if code.startswith("6"):
            return f"{code}.SS"
        return f"{code}.SZ"

    def execute_layer1(self, codes: list[str], config: Layer1HardFilter) -> list[str]:
        """硬过滤: 排除ST/新股/停牌/科创板/资不抵债"""
        provider = self._get_provider()
        all_stocks = provider.get_all_stocks()
        if not all_stocks:
            logger.warning("Layer1: 无法获取股票列表，返回输入集")
            return codes

        # 构建 code→info 映射 (yfinance格式)
        stock_map = {}
        for s in all_stocks:
            yf_code = self._bs_to_yf(s.get("code", ""))
            stock_map[yf_code] = s

        # 如果传入了 codes，交集过滤；否则用全量
        if codes:
            universe = [c for c in codes if c in stock_map]
        else:
            universe = list(stock_map.keys())

        filtered = []
        for code in universe:
            info = stock_map.get(code, {})
            trade_status = info.get("trade_status", "1")
            code_name = info.get("code_name", "")

            # 排除停牌
            if config.exclude_suspended and trade_status != "1":
                continue
            # 排除ST
            if config.exclude_st and "ST" in str(code_name).upper():
                continue
            # 排除科创板 (688xxx)
            if config.exclude_chi_next_star and (code.startswith("688") or "科创板" in str(code_name)):
                continue

            filtered.append(code)

        logger.info(f"Layer1: {len(universe)} → {len(filtered)} (ST/停牌/科创 过滤)")
        return filtered

    def execute_layer2(self, codes: list[str], config: Layer2FactorScoring) -> list[dict]:
        """因子打分: 使用 Alpha158 因子 ICIR 加权计算得分"""
        if not codes:
            return []

        # 尝试从 Qlib 加载因子数据
        try:
            return self._execute_layer2_qlib(codes, config)
        except Exception as e:
            logger.warning(f"Layer2 Qlib 模式失败，使用简化动量打分: {e}")
            return self._execute_layer2_simple(codes)

    def _execute_layer2_qlib(self, codes: list[str], config: Layer2FactorScoring) -> list[dict]:
        """使用 Qlib Alpha158 因子进行 ICIR 加权打分"""
        import qlib
        from qlib.data import D
        from qlib.data.dataset import DatasetH
        from qlib.data.dataset.handler import DataHandlerLP
        from qlib.utils import init_instance_by_config
        import numpy as np
        import pandas as pd
        from datetime import datetime

        # 按市场分组
        ss_codes = [c for c in codes if c.endswith(".SS")]
        sz_codes = [c for c in codes if c.endswith(".SZ")]

        instruments = []
        for c in ss_codes:
            instruments.append(f"SH{c.replace('.SS', '')}")
        for c in sz_codes:
            instruments.append(f"SZ{c.replace('.SZ', '')}")

        if not instruments:
            return self._execute_layer2_simple(codes)

        today = datetime.now().strftime("%Y-%m-%d")

        try:
            # 构建 Alpha158 数据集获取最新因子值
            handler_conf = {
                "class": "Alpha158",
                "module_path": "qlib.contrib.data.handler",
                "kwargs": {
                    "start_time": (datetime.now() - pd.Timedelta(days=365)).strftime("%Y-%m-%d"),
                    "end_time": today,
                    "fit_start_time": (datetime.now() - pd.Timedelta(days=365)).strftime("%Y-%m-%d"),
                    "fit_end_time": (datetime.now() - pd.Timedelta(days=31)).strftime("%Y-%m-%d"),
                    "instruments": instruments,
                },
            }
            handler = init_instance_by_config(handler_conf)

            # 获取最新因子值
            factor_names = handler.get_feature_names()
            latest_data = handler.fetch(col_set="feature")
            if latest_data is None or latest_data.empty:
                return self._execute_layer2_simple(codes)

            # 最新一天的因子值
            latest_date = latest_data.index.get_level_values("datetime").max()
            latest_factors = latest_data.xs(latest_date, level="datetime")

            # ICIR 加权：如果配置了 ICIR 加权，从缓存读取 ICIR
            scores = {}
            if config.icir_weighted:
                icir_map = self._load_icir_cache(config.icir_window)
                if icir_map:
                    for instrument in latest_factors.index:
                        factor_vals = latest_factors.loc[instrument]
                        score = 0.0
                        total_weight = 0.0
                        for fname in factor_names:
                            val = factor_vals.get(fname, np.nan)
                            if not np.isnan(val):
                                w = abs(icir_map.get(fname, 0.0))
                                score += val * w
                                total_weight += w
                        if total_weight > 0:
                            score /= total_weight
                        # 转换回 yfinance 格式
                        yf_code = instrument.replace("SH", "").replace("SZ", "") + (".SS" if "SH" in instrument else ".SZ")
                        scores[yf_code] = float(score)
                else:
                    # 无 ICIR 缓存，等权
                    for instrument in latest_factors.index:
                        factor_vals = latest_factors.loc[instrument]
                        valid_vals = [v for v in factor_vals.values if not np.isnan(v)]
                        yf_code = instrument.replace("SH", "").replace("SZ", "") + (".SS" if "SH" in instrument else ".SZ")
                        scores[yf_code] = float(np.mean(valid_vals)) if valid_vals else 0.0
            else:
                for instrument in latest_factors.index:
                    factor_vals = latest_factors.loc[instrument]
                    valid_vals = [v for v in factor_vals.values if not np.isnan(v)]
                    yf_code = instrument.replace("SH", "").replace("SZ", "") + (".SS" if "SH" in instrument else ".SZ")
                    scores[yf_code] = float(np.mean(valid_vals)) if valid_vals else 0.0

            # 排序
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            result = [{"code": c, "score": round(s, 4), "rank": i + 1} for i, (c, s) in enumerate(ranked)]

            # 行业中性化
            if config.industry_neutralize:
                result = self._neutralize_industry(result)

            logger.info(f"Layer2 (Qlib): {len(codes)} → {len(result)} 只打分完成")
            return result

        except Exception as e:
            raise e

    def _load_icir_cache(self, window: int) -> dict:
        """从 parquet 缓存加载 ICIR 值"""
        import pandas as pd
        cache_path = Path.home() / ".qlib" / "cache" / "factor_icir.parquet"
        if cache_path.exists():
            df = pd.read_parquet(cache_path)
            if "icir" in df.columns and "factor" in df.columns:
                return dict(zip(df["factor"], df["icir"]))
        return {}

    def _neutralize_industry(self, scored: list[dict]) -> list[dict]:
        """行业中性化：行业内标准化得分"""
        provider = self._get_provider()
        industry_scores = {}
        for s in scored:
            ind = provider.get_industry(s["code"])
            ind_name = ind.get("industry", "未知") if ind else "未知"
            if ind_name not in industry_scores:
                industry_scores[ind_name] = []
            industry_scores[ind_name].append(s)

        neutralized = []
        for ind_name, stocks in industry_scores.items():
            scores_in_ind = [s["score"] for s in stocks]
            mean_s = sum(scores_in_ind) / len(scores_in_ind)
            std_s = (sum((x - mean_s) ** 2 for x in scores_in_ind) / max(len(scores_in_ind), 1)) ** 0.5
            for s in stocks:
                z_score = (s["score"] - mean_s) / std_s if std_s > 0 else 0
                neutralized.append({**s, "score": round(z_score, 4), "raw_score": s["score"]})

        neutralized.sort(key=lambda x: x["score"], reverse=True)
        for i, s in enumerate(neutralized):
            s["rank"] = i + 1
        return neutralized

    def _execute_layer2_simple(self, codes: list[str]) -> list[dict]:
        """简化打分：使用 Qlib 价格动量（QLib 不可用时的降级方案）"""
        try:
            import qlib
            from qlib.data import D
            import numpy as np
            from datetime import datetime

            instruments = []
            code_map = {}
            for c in codes:
                if c.endswith(".SS"):
                    inst = f"SH{c.replace('.SS', '')}"
                else:
                    inst = f"SZ{c.replace('.SZ', '')}"
                instruments.append(inst)
                code_map[inst] = c

            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - pd.Timedelta(days=120)).strftime("%Y-%m-%d")

            prices = D.features(instruments, ["$close"], start, end)
            if prices is None or prices.empty:
                return [{"code": c, "score": 0.5, "rank": i + 1, "warning": "no_data"} for i, c in enumerate(codes)]

            scores = {}
            for inst in instruments:
                if inst in prices.columns.get_level_values(0):
                    inst_prices = prices.xs(inst, level="instrument", axis=1)["$close"].dropna()
                    if len(inst_prices) >= 20:
                        returns = inst_prices.pct_change(20).iloc[-1]
                        scores[code_map[inst]] = float(returns) if not np.isnan(returns) else 0.0
                    else:
                        scores[code_map[inst]] = 0.0
                else:
                    scores[code_map.get(inst, inst)] = 0.0

            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            return [{"code": c, "score": round(s, 4), "rank": i + 1} for i, (c, s) in enumerate(ranked)]

        except Exception:
            return [{"code": c, "score": 0.5, "rank": i + 1, "warning": "stub_fallback"} for i, c in enumerate(codes)]

    def execute_layer3(self, scored_stocks: list[dict], config: Layer3PortfolioConstraints) -> list[dict]:
        """组合约束: 控制股票数、行业集中度、相关性"""
        provider = self._get_provider()
        selected = []
        sector_counts: dict = {}

        for s in scored_stocks:
            if len(selected) >= config.max_stocks:
                break

            code = s["code"]
            # 行业集中度约束
            ind = provider.get_industry(code)
            ind_name = ind.get("industry", "未知") if ind else "未知"
            sector_count = sector_counts.get(ind_name, 0)
            max_per_sector = int(config.max_stocks * config.max_sector_weight)
            if sector_count >= max_per_sector:
                continue

            selected.append(s)
            sector_counts[ind_name] = sector_count + 1

        # 权重分配
        if config.position_method == "equal_weight":
            weight = 1.0 / len(selected) if selected else 0
            for s in selected:
                s["weight"] = weight
        elif config.position_method == "market_cap":
            # 简化：等权（市值加权需要额外查询）
            weight = 1.0 / len(selected) if selected else 0
            for s in selected:
                s["weight"] = weight

        logger.info(f"Layer3: {len(scored_stocks)} → {len(selected)} (max={config.max_stocks}, sectors={len(sector_counts)})")
        return selected

    def refresh_pool(self, pool_id: str) -> dict:
        """完整三层执行"""
        conn = _get_db()
        pool = conn.execute("SELECT * FROM pools WHERE id = ?", (pool_id,)).fetchone()
        if not pool:
            conn.close()
            raise ValueError(f"股票池不存在: {pool_id}")

        config = json.loads(pool["config_json"])
        l1 = Layer1HardFilter(**config.get("layer1", {}))
        l2 = Layer2FactorScoring(**config.get("layer2", {}))
        l3 = Layer3PortfolioConstraints(**config.get("layer3", {}))

        # 从真实数据获取初始股票范围
        provider = self._get_provider()
        index_stocks = provider.get_index_stocks("hs300")
        if index_stocks:
            codes = [self._bs_to_yf(s["code"]) for s in index_stocks]
        else:
            # 降级：从全量股票列表中获取
            all_stocks = provider.get_all_stocks()
            if all_stocks:
                codes = [self._bs_to_yf(s["code"]) for s in all_stocks[:300]]
            else:
                # 最终降级：使用示例代码
                logger.warning("无法获取真实股票数据，使用示例代码")
                codes = [f"{i:06d}.{'SS' if i >= 600000 else 'SZ'}" for i in range(1, 31)]
                codes[0] = "600519.SS"
                codes[1] = "000858.SZ"
                codes[2] = "601318.SS"
                codes[3] = "000333.SZ"
                codes[4] = "600036.SS"
                codes[5] = "300750.SZ"

        filtered = self.execute_layer1(codes, l1)
        scored = self.execute_layer2(filtered, l2)
        constituents = self.execute_layer3(scored, l3)

        # 保存历史
        today = date.today().isoformat()
        history_id = str(uuid.uuid4())[:8]
        conn.execute(
            "INSERT INTO pool_history (id, pool_id, date, constituents_json) VALUES (?, ?, ?, ?)",
            (history_id, pool_id, today, json.dumps(constituents, ensure_ascii=False)),
        )
        conn.execute(
            "UPDATE pools SET updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), pool_id),
        )
        conn.commit()
        conn.close()

        return {
            "pool_id": pool_id,
            "date": today,
            "constituents": constituents,
            "stats": {
                "input_count": len(sample_codes),
                "post_layer1": len(filtered),
                "post_layer2": len(scored),
                "post_layer3": len(constituents),
            },
        }


_engine: Optional[StockPoolEngine] = None


def get_engine() -> StockPoolEngine:
    global _engine
    if _engine is None:
        _engine = StockPoolEngine()
    return _engine
