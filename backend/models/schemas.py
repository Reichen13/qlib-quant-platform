"""
Pydantic 数据模型
定义 API 请求和响应的数据结构
"""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ── 通用响应模型 ──
class ApiResponse(BaseModel):
    """通用 API 响应"""
    success: bool
    message: Optional[str] = None
    data: Optional[dict] = None


# ── 股票相关模型 ──
class StockInfo(BaseModel):
    """股票信息"""
    code: str = Field(..., description="股票代码，如 SH600519")
    name: str = Field(..., description="股票名称")
    market: str = Field(..., description="市场：SH 或 SZ")
    transparency: str = Field(..., description="透明度级别：HIGH, MEDIUM, LOW")


class StockListResponse(BaseModel):
    """股票列表响应"""
    total: int
    stocks: List[StockInfo]


class StockSearchRequest(BaseModel):
    """股票搜索请求"""
    query: str = Field(..., min_length=1, description="搜索关键词")


# ── 行情相关模型 ──
class QuoteData(BaseModel):
    """行情数据点"""
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: Optional[float] = None


class IndicatorData(BaseModel):
    """技术指标数据"""
    date: date
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None


class QuoteResponse(BaseModel):
    """行情响应"""
    code: str
    name: str
    data: List[QuoteData]
    indicators: Optional[List[IndicatorData]] = None


# ── 板块相关模型 ──
class SectorInfo(BaseModel):
    """板块信息"""
    name: str
    change_pct: float
    volume: Optional[float] = None
    stock_count: int


class SectorStockInfo(BaseModel):
    """板块内股票信息"""
    code: str
    name: str
    change_pct: float
    volume: float
    factor_score: Optional[float] = None


class SectorDetailResponse(BaseModel):
    """板块详情响应"""
    sector: SectorInfo
    stocks: List[SectorStockInfo]


class HotSectorsResponse(BaseModel):
    """热门板块响应"""
    date: date
    sectors: List[SectorInfo]


# ── 因子分析模型 ──
class FactorIC(BaseModel):
    """因子 IC 值（增强统计面板）"""
    factor: str
    ic: float
    rank_ic: float
    icir: float
    category: str = Field(default="未分类", description="因子类别")
    # 增强统计（向后兼容，全部 optional）
    skewness: Optional[float] = Field(default=None, description="IC 偏度")
    kurtosis: Optional[float] = Field(default=None, description="IC 超额峰度")
    t_statistic: Optional[float] = Field(default=None, description="t 统计量")
    p_value: Optional[float] = Field(default=None, description="p 值")
    information_ratio: Optional[float] = Field(default=None, description="信息比率")
    ic_autocorr: Optional[float] = Field(default=None, description="IC lag-1 自相关")
    industry_contribution: Optional[dict] = Field(default=None, description="行业加权 IC 贡献")


class FactorAnalysisRequest(BaseModel):
    """因子分析请求"""
    start_date: date
    end_date: date
    predict_period: int = Field(default=5, ge=1, le=20, description="预测周期（天）")
    top_k: int = Field(default=20, ge=5, le=158, description="显示前 K 个因子（Alpha158 最多 158）")
    neutralize: Optional[str] = Field(default=None, description="中性化方法: 'industry' 行业中性化, None 不中性化")


class FactorAnalysisResponse(BaseModel):
    """因子分析响应"""
    start_date: date
    end_date: date
    predict_period: int
    factors: List[FactorIC]
    summary: dict


# ── 回测模型 ──
class BacktestParams(BaseModel):
    """回测参数"""
    # 模型设置
    model: str = Field(default="lightgbm", description="模型类型: lightgbm, xgboost")

    # 数据设置
    train_start: date
    train_end: date
    test_start: date
    test_end: date

    # 策略参数
    hold_num: int = Field(default=30, ge=1, le=50, description="持仓股票数(TopK)")
    turnover: int = Field(default=5, ge=1, le=20, description="调仓周期(天)")

    # 风险控制
    max_position: float = Field(default=0.05, ge=0.01, le=0.3, description="单票最大仓位")
    stop_loss: float = Field(default=-0.08, le=0, description="止损比例")

    # 交易成本
    buy_cost: float = Field(default=0.0003, ge=0, le=0.01, description="买入佣金")
    sell_cost: float = Field(default=0.0003, ge=0, le=0.01, description="卖出佣金")


class EquityPoint(BaseModel):
    """净值曲线数据点"""
    date: str
    value: float
    benchmark: float


class DrawdownPoint(BaseModel):
    """回撤曲线数据点"""
    date: str
    value: float


class StockRecommendation(BaseModel):
    """股票推荐"""
    code: str
    name: str
    score: float
    reason: str


class BacktestResponse(BaseModel):
    """回测响应"""
    task_id: str
    status: str  # running, completed, failed
    progress: Optional[int] = None
    # 收益指标
    total_return: Optional[float] = None
    annual_return: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    win_rate: Optional[float] = None
    profit_loss_ratio: Optional[float] = None
    # 统计检验
    t_statistic: Optional[float] = None
    p_value: Optional[float] = None
    information_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    monthly_win_rate: Optional[float] = None
    # 曲线数据
    equity: Optional[List[EquityPoint]] = None
    drawdown: Optional[List[DrawdownPoint]] = None
    # 推荐
    top_buys: Optional[List[StockRecommendation]] = None
    top_sells: Optional[List[StockRecommendation]] = None
    position_advice: Optional[str] = None
    # A 股约束分析
    constraint_analysis: Optional[dict] = None
    # 错误信息
    error: Optional[str] = None


# ── ETF 相关模型 ──
class ETFInfo(BaseModel):
    """ETF 信息"""
    code: str
    name: str
    price: float
    change_pct: float
    volume: float
    signal: str  # buy, hold, sell


class ETFSignalResponse(BaseModel):
    """ETF 信号响应"""
    date: date
    etfs: List[ETFInfo]
    top_buy: List[str]
    top_sell: List[str]


# ── 数据状态模型 ──
class DataStatus(BaseModel):
    """数据状态"""
    qlib_initialized: bool
    qlib_data_dir: str
    qlib_start_date: Optional[date] = None
    qlib_end_date: Optional[date] = None
    stock_count: int
    last_update: Optional[datetime] = None


# ── 风险管理模型 ──
class RiskAnalysisRequest(BaseModel):
    """风险分析请求"""
    codes: List[str] = Field(default=[], description="股票代码列表，如 ['600519.SS', '000858.SZ']")
    start_date: Optional[str] = Field(default=None, description="开始日期 YYYY-MM-DD，默认一年前")
    end_date: Optional[str] = Field(default=None, description="结束日期 YYYY-MM-DD，默认今天")


class RiskMetrics(BaseModel):
    """风险指标"""
    annual_return: float
    annual_volatility: float
    sharpe_ratio: float
    calmar_ratio: float
    max_drawdown: float
    win_rate: float
    var_95: float
    cvar_95: float
    var_99: float
    cvar_99: float
    avg_correlation: float
    vol_cone: dict = Field(default={}, description="波动率锥")


class StressTestResult(BaseModel):
    """压力测试结果"""
    name: str
    description: str
    impact: float  # 百分比
    scenario_type: str  # historical / hypothetical / historical_proxy


class CorrelationItem(BaseModel):
    """相关性项"""
    stock1: str
    stock2: str
    correlation: float


class PositionSizingResult(BaseModel):
    """头寸规模结果"""
    kelly_fraction: float
    half_kelly: float
    quarter_kelly: float
    risk_level: str
    suggestion: str


class RiskAnalysisResponse(BaseModel):
    """风险分析响应"""
    codes: List[str]
    start_date: str
    end_date: str
    metrics: RiskMetrics
    stress_tests: List[StressTestResult]
    correlations: List[CorrelationItem]
    position_sizing: PositionSizingResult
    equity: List[dict] = []
    drawdown: List[dict] = []


# ── 投资组合优化模型 ──
class PortfolioOptimizeRequest(BaseModel):
    """组合优化请求"""
    codes: List[str] = Field(..., description="股票代码列表")
    start_date: Optional[str] = Field(default=None, description="开始日期")
    end_date: Optional[str] = Field(default=None, description="结束日期")
    method: str = Field(default="max_sharpe", description="优化方法: max_sharpe, min_variance, risk_parity, equal_weight")
    max_weight: float = Field(default=0.3, ge=0.01, le=1.0, description="单票最大权重")


class PortfolioWeight(BaseModel):
    """持仓权重"""
    code: str
    weight: float


class EfficientFrontierPoint(BaseModel):
    """有效前沿数据点"""
    ret: float
    volatility: float
    sharpe: float


class PortfolioOptimizeResponse(BaseModel):
    """组合优化响应"""
    codes: List[str]
    start_date: str
    end_date: str
    method: str
    weights: List[PortfolioWeight]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    diversification_ratio: float
    efficient_frontier: List[EfficientFrontierPoint]
    benchmark: dict


# ── 宏观策略模型 ──

class MacroIndicator(BaseModel):
    """宏观指标数据点"""
    name: str = Field(..., description="指标名称")
    symbol: str = Field(..., description="yfinance symbol")
    value: float = Field(..., description="当前值")
    change_pct: float = Field(..., description="日涨跌幅")
    trend: str = Field(default="flat", description="趋势方向")
    z_score: float = Field(default=0, description="标准化得分")


class MacroRegimeRequest(BaseModel):
    """市场状态分类请求"""
    indicators: dict = Field(default={}, description="指标数据字典")


class MacroRegimeResponse(BaseModel):
    """市场状态分类响应"""
    growth_score: float = Field(..., description="增长得分")
    inflation_score: float = Field(..., description="通胀得分")
    regime: str = Field(..., description="状态标识")
    regime_label: str = Field(..., description="状态中文标签")
    confidence: float = Field(default=0.5, description="置信度")
    quadrant: str = Field(default="Q1", description="象限")


class AllocationAsset(BaseModel):
    """配置资产"""
    asset: str = Field(..., description="资产类别")
    weight: float = Field(..., description="建议权重")
    reason: str = Field(default="", description="配置理由")


class AllocationResponse(BaseModel):
    """全天候配置建议"""
    regime: str = Field(..., description="当前状态")
    regime_label: str = Field(..., description="状态中文标签")
    allocation: List[AllocationAsset] = Field(..., description="资产配置方案")
    risk_level: str = Field(default="中性", description="风险等级")
    summary: str = Field(default="", description="配置总结")
