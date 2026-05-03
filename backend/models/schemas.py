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
    """因子 IC 值"""
    factor: str
    ic: float
    rank_ic: float
    icir: float


class FactorAnalysisRequest(BaseModel):
    """因子分析请求"""
    start_date: date
    end_date: date
    predict_period: int = Field(default=5, ge=1, le=20, description="预测周期（天）")
    top_k: int = Field(default=20, ge=5, le=158, description="显示前 K 个因子（Alpha158 最多 158）")


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
    # 曲线数据
    equity: Optional[List[EquityPoint]] = None
    drawdown: Optional[List[DrawdownPoint]] = None
    # 推荐
    top_buys: Optional[List[StockRecommendation]] = None
    top_sells: Optional[List[StockRecommendation]] = None
    position_advice: Optional[str] = None
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
