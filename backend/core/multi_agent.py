"""
多智能体协作/辩论编排核心

5 阶段管道（参考 TradingAgents 架构）:
  Stage 1: 分析师团队 (并行) — 技术面/基本面/情绪面/宏观面
  Stage 2: 研究员辩论 — 多头 vs 空头 + 研究主管裁判
  Stage 3: 交易员 — 交易提案 (方向/入场价/止损/仓位)
  Stage 4: 风控辩论 — 激进 vs 保守 vs 中性 + 风控主管裁判
  Stage 5: 投资组合经理 (PM) — 最终决策

记忆系统: ~/.qlib/agent_memory/{ticker}/ 追加式 Markdown
"""

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field
from utils.code_normalization import normalize_stock_code


# ── 结构化输出模型 ──

class AnalystReport(BaseModel):
    analyst: str = ""
    summary: str = ""
    key_findings: list[str] = Field(default_factory=list)
    bullish_factors: list[str] = Field(default_factory=list)
    bearish_factors: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class ResearchPlan(BaseModel):
    verdict: str = ""  # bullish / bearish / neutral
    thesis: str = ""
    key_catalysts: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)


class TradeProposal(BaseModel):
    direction: str = ""  # long / short / hold
    entry_price: str = ""
    stop_loss: str = ""
    take_profit: str = ""
    position_pct: float = 0.0
    rationale: str = ""


class RiskAssessment(BaseModel):
    risk_level: str = ""  # low / medium / high
    var_estimate: str = ""
    key_concerns: list[str] = Field(default_factory=list)
    mitigation: list[str] = Field(default_factory=list)


class PortfolioDecision(BaseModel):
    rating: str = ""  # 强力买入 / 买入 / 持有 / 卖出 / 强力卖出
    thesis: str = ""
    price_target: str = ""
    risk_alerts: list[str] = Field(default_factory=list)
    position_sizing: str = ""
    time_horizon: str = ""


class AgentReport(BaseModel):
    task_id: str
    code: str
    timestamp: str
    stage1_analysts: list[AnalystReport] = Field(default_factory=list)
    stage2_debate: Optional[ResearchPlan] = None
    stage3_trade: Optional[TradeProposal] = None
    stage4_risk: Optional[RiskAssessment] = None
    stage5_decision: Optional[PortfolioDecision] = None


# ── 工具函数（封装后端 API 数据）──

def _get_stock_info(code: str) -> dict:
    """获取股票基本信息 — 连接真实数据"""
    try:
        from services.data_provider import DataProvider
        provider = DataProvider()
        summary = provider.get_financial_summary(code)
        if summary:
            return {
                "code": code,
                "source": "baostock",
                "financials": {
                    "profit": summary.get("profit"),
                    "growth": summary.get("growth"),
                    "operation": summary.get("operation"),
                },
            }
    except Exception:
        pass
    return {"code": code, "source": "unavailable"}


def _format_financials(code: str) -> str:
    """获取财务数据摘要 — 连接真实数据"""
    try:
        from services.data_provider import DataProvider
        provider = DataProvider()
        summary = provider.get_financial_summary(code)
        if summary:
            profit = summary.get("profit") or {}
            growth = summary.get("growth") or {}
            operation = summary.get("operation") or {}
            lines = [f"=== {code} 财务数据 ==="]
            if profit:
                lines.append(f"ROE: {profit.get('roe', 'N/A')}%")
                lines.append(f"净利率: {profit.get('npMargin', 'N/A')}%")
                lines.append(f"毛利率: {profit.get('gpMargin', 'N/A')}%")
            if growth:
                lines.append(f"净利润增长率: {growth.get('YOYNI', 'N/A')}%")
            if operation:
                lines.append(f"总资产周转率: {operation.get('TATurnRatio', 'N/A')}")
            return "\n".join(lines)
    except Exception:
        pass
    return f"财务数据({code}): 暂不可用"


def _format_indicators(code: str) -> str:
    """获取技术指标摘要 — 连接真实数据"""
    try:
        import qlib
        from qlib.data import D
        import numpy as np
        import pandas as pd
        from datetime import datetime

        inst = normalize_stock_code(code, target="qlib")
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - pd.Timedelta(days=120)).strftime("%Y-%m-%d")

        prices = D.features([inst], ["$close"], start, end)
        if prices is not None and not prices.empty:
            close = prices.xs(inst, level="instrument", axis=1)["$close"].dropna()
            if len(close) >= 20:
                # 计算指标
                delta = close.diff()
                gain = delta.clip(lower=0)
                loss = -delta.clip(upper=0)
                avg_gain = gain.rolling(14).mean()
                avg_loss = loss.rolling(14).mean()
                rs = avg_gain / avg_loss.replace(0, np.nan)
                rsi = 100 - (100 / (1 + rs))
                ma5 = close.rolling(5).mean()
                ma20 = close.rolling(20).mean()

                latest_close = float(close.iloc[-1])
                latest_rsi = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else None
                latest_ma5 = float(ma5.iloc[-1]) if not np.isnan(ma5.iloc[-1]) else None
                latest_ma20 = float(ma20.iloc[-1]) if not np.isnan(ma20.iloc[-1]) else None
                ret_20d = float((close.iloc[-1] / close.iloc[-20] - 1) * 100) if len(close) >= 20 else None

                lines = [f"=== {code} 技术指标 ==="]
                lines.append(f"最新收盘价: {latest_close:.2f}")
                lines.append(f"RSI(14): {latest_rsi:.1f}" if latest_rsi else "RSI(14): N/A")
                lines.append(f"MA5: {latest_ma5:.2f}" if latest_ma5 else "MA5: N/A")
                lines.append(f"MA20: {latest_ma20:.2f}" if latest_ma20 else "MA20: N/A")
                lines.append(f"20日涨跌幅: {ret_20d:.1f}%" if ret_20d else "20日涨跌幅: N/A")
                lines.append("趋势: " + ("上涨" if latest_ma5 and latest_ma20 and latest_ma5 > latest_ma20 else "下跌/震荡"))
                return "\n".join(lines)
    except Exception:
        pass
    return f"技术指标({code}): 暂不可用"


# ── Agent 执行器 ──

class AgentOrchestrator:
    """多智能体编排器"""

    def __init__(self):
        self._memory_base = Path.home() / ".qlib" / "agent_memory"
        self._llm_client = None  # 可选的 per-request LLM client

    def set_llm_client(self, client):
        """设置 per-request LLM 客户端（用户自己的 API key）"""
        self._llm_client = client

    def _check_llm(self):
        if self._llm_client:
            return
        from core.llm_client import get_llm_config
        if not get_llm_config().is_configured:
            raise RuntimeError("LLM 未配置")

    def _get_llm(self, deep: bool = False):
        if self._llm_client:
            return self._llm_client.get_deep_llm() if deep else self._llm_client.get_quick_llm()
        from core.llm_client import get_llm_client
        client = get_llm_client()
        return client.get_deep_llm() if deep else client.get_quick_llm()

    def _invoke_json(self, prompt: str, system: str = "", deep: bool = False) -> str:
        """调用 LLM 并返回文本"""
        self._check_llm()
        llm = self._get_llm(deep)
        messages = []
        if system:
            messages.append(("system", system))
        messages.append(("user", prompt))
        response = llm.invoke(messages)
        return response.content if hasattr(response, "content") else str(response)

    def _parse_json(self, text: str) -> dict:
        """从 LLM 输出中提取 JSON"""
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        return {}

    # ── Stage 1: 分析师团队 ──

    def _run_analyst(self, code: str, role: str, instructions: str) -> AnalystReport:
        prompt = f"""你是{role}。请分析股票 {code}。

分析要求: {instructions}

请返回 JSON:
{{
  "analyst": "{role}",
  "summary": "分析摘要（中文，100字以内）",
  "key_findings": ["发现1", "发现2", "发现3"],
  "bullish_factors": ["看多因素1", "看多因素2"],
  "bearish_factors": ["看空因素1", "看空因素2"],
  "confidence": 0.0-1.0
}}"""
        system = f"你是一位资深的{role}，专注于A股市场分析。回答简洁专业，用中文。"
        text = self._invoke_json(prompt, system)
        data = self._parse_json(text)
        if data:
            return AnalystReport(**data)
        return AnalystReport(analyst=role, summary=text[:200])

    def stage1_analysts(self, code: str) -> list[AnalystReport]:
        """并行运行 4 个分析师（注入真实数据）"""
        logger.info(f"Stage 1: 分析师团队开始分析 {code}")

        # 获取真实数据
        stock_info = _get_stock_info(code)
        financials_text = _format_financials(code)
        indicators_text = _format_indicators(code)

        roles = [
            ("技术面分析师",
             f"分析价格趋势、均线、RSI、MACD、成交量等技术指标，判断短期和中期走势。\n\n"
             f"【真实技术数据】\n{indicators_text}"),
            ("基本面分析师",
             f"分析PE/PB估值、ROE、营收增速、毛利率、负债率等财务指标，评估内在价值。\n\n"
             f"【真实财务数据】\n{financials_text}"),
            ("情绪面分析师",
             f"分析近期新闻情绪、市场关注度、北向资金流向、融资余额变化。\n\n"
             f"【已知信息】股票代码: {code}, 数据源: {stock_info.get('source', 'unavailable')}"),
            ("宏观面分析师",
             "分析当前货币政策、经济周期、行业政策、外部环境对A股的影响（2025年中国经济背景：GDP增速约5%，"
             "CPI低位运行，货币政策稳中偏松，AI/新能源/高端制造为政策重点支持方向）"),
        ]

        reports = []
        for role, instructions in roles:
            try:
                report = self._run_analyst(code, role, instructions)
                reports.append(report)
            except Exception as e:
                logger.warning(f"分析师 {role} 失败: {e}")
                reports.append(AnalystReport(analyst=role, summary=f"分析失败: {e}"))

        return reports

    # ── Stage 2: 研究员辩论 ──

    def stage2_debate(self, code: str, analyst_reports: list[AnalystReport]) -> ResearchPlan:
        """多头 vs 空头辩论 + 研究主管裁判"""
        logger.info(f"Stage 2: 研究员辩论 {code}")

        # 汇总分析师发现
        all_bullish = []
        all_bearish = []
        for r in analyst_reports:
            all_bullish.extend(r.bullish_factors)
            all_bearish.extend(r.bearish_factors)

        prompt = f"""你是研究主管。以下是股票 {code} 的分析师团队发现:

看多因素: {json.dumps(all_bullish[:10], ensure_ascii=False)}
看空因素: {json.dumps(all_bearish[:10], ensure_ascii=False)}

请综合各方观点，用 deep reasoning 做出研究判断。

返回 JSON:
{{
  "verdict": "bullish/bearish/neutral",
  "thesis": "核心投资逻辑（中文，150字以内）",
  "key_catalysts": ["催化剂1", "催化剂2"],
  "key_risks": ["风险1", "风险2"]
}}"""

        text = self._invoke_json(prompt, deep=True)
        data = self._parse_json(text)
        if data:
            return ResearchPlan(**data)
        return ResearchPlan(verdict="neutral", thesis=text[:200])

    # ── Stage 3: 交易员 ──

    def stage3_trader(self, code: str, research_plan: ResearchPlan) -> TradeProposal:
        """交易提案"""
        logger.info(f"Stage 3: 交易员提案 {code}")

        prompt = f"""你是交易员。基于以下研究计划，制定交易提案:

股票: {code}
研究方向: {research_plan.verdict}
投资逻辑: {research_plan.thesis}
催化剂: {json.dumps(research_plan.key_catalysts, ensure_ascii=False)}
风险: {json.dumps(research_plan.key_risks, ensure_ascii=False)}

返回 JSON:
{{
  "direction": "long/short/hold",
  "entry_price": "建议入场价或'市价'",
  "stop_loss": "止损价位",
  "take_profit": "止盈价位",
  "position_pct": 0.0-0.3 的建议仓位比例,
  "rationale": "交易理由（中文，50字以内）"
}}"""

        text = self._invoke_json(prompt)
        data = self._parse_json(text)
        if data:
            return TradeProposal(**data)
        return TradeProposal(direction="hold", rationale=text[:200])

    # ── Stage 4: 风控辩论 ──

    def stage4_risk(self, code: str, trade: TradeProposal) -> RiskAssessment:
        """风控辩论"""
        logger.info(f"Stage 4: 风控评估 {code}")

        prompt = f"""你是风控主管。请从激进、保守、中性三个角度审视以下交易提案:

股票: {code}
方向: {trade.direction}
仓位: {trade.position_pct}
止损: {trade.stop_loss}

请给出最终风控评估。

返回 JSON:
{{
  "risk_level": "low/medium/high",
  "var_estimate": "估计 VaR 描述",
  "key_concerns": ["关注点1", "关注点2"],
  "mitigation": ["缓释措施1", "缓释措施2"]
}}"""

        text = self._invoke_json(prompt, deep=True)
        data = self._parse_json(text)
        if data:
            return RiskAssessment(**data)
        return RiskAssessment(risk_level="medium", key_concerns=[text[:200]])

    # ── Stage 5: PM 最终决策 ──

    def stage5_pm(
        self,
        code: str,
        analyst_reports: list[AnalystReport],
        research_plan: ResearchPlan,
        trade: TradeProposal,
        risk: RiskAssessment,
    ) -> PortfolioDecision:
        """投资组合经理最终决策"""
        logger.info(f"Stage 5: PM 最终决策 {code}")

        prompt = f"""你是资深投资组合经理。请综合以下全部信息，做出最终投资决策:

=== 股票: {code} ===

【分析师团队】
{chr(10).join(f"- {r.analyst}: {r.summary}" for r in analyst_reports)}

【研究主管结论】{research_plan.verdict}
投资逻辑: {research_plan.thesis}

【交易员提案】
方向: {trade.direction}, 仓位: {trade.position_pct}
入场: {trade.entry_price}, 止损: {trade.stop_loss}

【风控评估】
风险等级: {risk.risk_level}
关注点: {', '.join(risk.key_concerns)}

返回 JSON:
{{
  "rating": "强力买入/买入/持有/卖出/强力卖出",
  "thesis": "综合投资逻辑（中文，150字以内）",
  "price_target": "目标价位或区间",
  "risk_alerts": ["风险1", "风险2"],
  "position_sizing": "仓位建议（如'总仓位5-10%，分2次建仓'）",
  "time_horizon": "投资期限（如'中线持有2-3个月'）"
}}"""

        text = self._invoke_json(prompt, deep=True)
        data = self._parse_json(text)
        if data:
            return PortfolioDecision(**data)
        return PortfolioDecision(rating="持有", thesis=text[:200])

    # ── 完整管道 ──

    def run_full_pipeline(self, code: str) -> AgentReport:
        """运行完整的 5 阶段管道"""
        task_id = str(uuid.uuid4())[:8]

        # Stage 1
        analyst_reports = self.stage1_analysts(code)

        # Stage 2
        research_plan = self.stage2_debate(code, analyst_reports)

        # Stage 3
        trade = self.stage3_trader(code, research_plan)

        # Stage 4
        risk = self.stage4_risk(code, trade)

        # Stage 5
        decision = self.stage5_pm(code, analyst_reports, research_plan, trade, risk)

        report = AgentReport(
            task_id=task_id,
            code=code,
            timestamp=datetime.now().isoformat(),
            stage1_analysts=analyst_reports,
            stage2_debate=research_plan,
            stage3_trade=trade,
            stage4_risk=risk,
            stage5_decision=decision,
        )

        # 保存记忆
        self._save_memory(code, report)

        return report

    # ── 记忆系统 ──

    def _save_memory(self, code: str, report: AgentReport):
        """追加式记忆保存"""
        try:
            ticker = code.replace(".SS", "").replace(".SZ", "")
            mem_dir = self._memory_base / ticker
            mem_dir.mkdir(parents=True, exist_ok=True)

            mem_file = mem_dir / "memory.md"
            entry = f"""## {report.timestamp}

**评级**: {report.stage5_decision.rating}
**逻辑**: {report.stage5_decision.thesis}
**风控**: {report.stage4_risk.risk_level}

---
"""
            with open(mem_file, "a") as f:
                f.write(entry)
        except Exception as e:
            logger.warning(f"记忆保存失败: {e}")

    def get_memory(self, code: str) -> str:
        """读取历史记忆"""
        ticker = code.replace(".SS", "").replace(".SZ", "")
        mem_file = self._memory_base / ticker / "memory.md"
        if mem_file.exists():
            return mem_file.read_text()
        return ""


# 模块级单例
_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
