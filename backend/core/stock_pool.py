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

    def execute_layer1(self, codes: list[str], config: Layer1HardFilter) -> list[str]:
        """硬过滤: 排除不符合基本条件的股票（桩实现）

        完整实现需要从 Qlib/baostock 获取个股基本面数据。
        """
        return codes  # 桩: 返回全部输入

    def execute_layer2(self, codes: list[str], config: Layer2FactorScoring) -> list[dict]:
        """因子打分: 计算每只股票的综合得分（桩实现）

        完整实现需要加载 Qlib Alpha158 因子数据并计算加权得分。
        """
        return [{"code": c, "score": 0.5, "rank": i + 1} for i, c in enumerate(codes)]

    def execute_layer3(self, scored_stocks: list[dict], config: Layer3PortfolioConstraints) -> list[dict]:
        """组合约束: 输出最终成分 + 权重（桩实现）"""
        selected = scored_stocks[:config.max_stocks]
        if config.position_method == "equal_weight":
            weight = 1.0 / len(selected) if selected else 0
            return [{"code": s["code"], "weight": weight, "score": s["score"]} for s in selected]
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

        # 桩: 使用 CSI300 作为初始股票范围
        sample_codes = [f"{i:06d}.{'SS' if i >= 600000 else 'SZ'}" for i in range(1, 31)]
        filtered = self.execute_layer1(sample_codes, l1)
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
