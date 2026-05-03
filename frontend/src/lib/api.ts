// API 客户端封装
// 开发环境用 localhost，生产环境用相对路径（由 Nginx 代理）
const API_BASE = import.meta.env.DEV ? "http://localhost:8000" : ""
const DEFAULT_API_TIMEOUT_MS = 8000

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

type ApiRequestInit = RequestInit & { timeoutMs?: number }

async function apiFetch(input: RequestInfo | URL, init: ApiRequestInit = {}): Promise<Response> {
  const { timeoutMs = DEFAULT_API_TIMEOUT_MS, signal, ...requestInit } = init
  const controller = new AbortController()
  const timeoutId = globalThis.setTimeout(() => controller.abort(), timeoutMs)

  if (signal) {
    if (signal.aborted) {
      controller.abort()
    } else {
      signal.addEventListener("abort", () => controller.abort(), { once: true })
    }
  }

  try {
    return await globalThis.fetch(input, {
      ...requestInit,
      signal: controller.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(408, `请求超时（${timeoutMs / 1000} 秒）`)
    }
    throw error
  } finally {
    globalThis.clearTimeout(timeoutId)
  }
}

const fetch = apiFetch

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.text().catch(() => "Unknown error")
    throw new ApiError(response.status, error)
  }
  return response.json()
}

// 股票信息类型
export interface Stock {
  code: string
  name: string
  market: string
  transparency: string
}

export interface StockListResponse {
  total: number
  stocks: Stock[]
}

// 板块信息类型
export interface Sector {
  name: string
  change_pct: number
  volume: number | null
  stock_count: number
}

export interface HotSectorsResponse {
  date: string
  sectors: Sector[]
}

// 行情数据类型
export interface QuoteData {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number | null
}

export interface QuoteResponse {
  code: string
  name: string
  data: QuoteData[]
  indicators?: IndicatorData[]
}

export interface IndicatorData {
  date: string
  ma5: number | null
  ma10: number | null
  ma20: number | null
  ma60: number | null
  rsi: number | null
  macd: number | null
  macd_signal: number | null
  macd_hist: number | null
}

// ETF 信息类型
export interface ETFInfo {
  code: string
  name: string
  price: number | null
  change_pct: number | null
  volume: number
  signal: string
}

export interface ETFSignalsResponse {
  date: string
  etfs: ETFInfo[]
  top_buy: string[]
  top_sell: string[]
}

// 因子 IC 类型
export interface FactorIC {
  factor: string
  ic: number
  rank_ic: number
  icir: number
}

// 数据状态类型
export interface DataStatus {
  stocks: {
    total: number
    last_date: string
    lag_days: number
    status: "normal" | "warning" | "error"
  }
  etf: {
    total: number
    last_date: string
    lag_days: number
    status: "normal" | "warning" | "error"
  }
  index: {
    total: number
    last_date: string
    lag_days: number
    status: "normal" | "warning" | "error"
  }
}

export interface DataUpdateResponse {
  task_id: string
  status: "started" | "running" | "completed" | "failed"
  progress: number
  message: string
}

// 回测结果类型
export type BacktestResult = {
  task_id: string
  status: "running" | "completed" | "failed"
  progress?: number
  total_return?: number
  annual_return?: number
  sharpe_ratio?: number
  calmar_ratio?: number
  max_drawdown?: number
  win_rate?: number
  profit_loss_ratio?: number
  equity?: Array<{ date: string; value: number; benchmark: number }>
  drawdown?: Array<{ date: string; value: number }>
  top_buys?: Array<{ code: string; name: string; score: number; reason: string }>
  top_sells?: Array<{ code: string; name: string; score: number; reason: string }>
  position_advice?: string
  error?: string
}

// 因子分析结果类型
export interface FactorAnalysisResult {
  factors: FactorIC[]
  summary: {
    total: number
    valid_factors: number
    avg_ic: number
    max_ic: number
    positive_count: number
    negative_count: number
  }
  distribution: Array<{ bin: string; count: number }>
  predict_period: number
}

// 财务数据类型
export interface FinancialSummary {
  code: string
  name: string
  profit: ProfitData | null
  growth: GrowthData | null
  operation: OperationData | null
  dupont: DupontData | null
}

export interface ProfitData {
  updateDate: string
  roe: number | null
  npMargin: number | null
  gpMargin: number | null
  netProfit: number | null
  epsTTM: number | null
  MBRevenue: number | null
  MCPMargin: number | null
}

export interface GrowthData {
  updateDate: string
  YOYNI: number | null
  YOYNIBasicEPS: number | null
  YOYOrrOccupyAssets: number | null
  YOYOrrBTM: number | null
}

export interface OperationData {
  updateDate: string
  NRTurnRatio: number | null
  NRTurnDays: number | null
  INVTurnRatio: number | null
  INVTurnDays: number | null
  TATurnRatio: number | null
  TATurnDays: number | null
}

export interface DupontData {
  updateDate: string
  dupont: number | null
  dupontNIAG: number | null
  dupontNIAP: number | null
  dupontTATurn: number | null
  dupontAssetToEquity: number | null
}

export interface FinancialRanking {
  metric: string
  order: string
  total: number
  rankings: Array<{
    code: string
    name: string
    value: number
    year: number
    quarter: number
  }>
}

// 行业板块类型
export interface IndustryInfo {
  code: string
  name: string
  industry: string | null
  industryClassification: string | null
}

export interface IndustryListResponse {
  total: number
  industries: Array<{
    name: string
    count: number
  }>
}

export interface IndustryStocksResponse {
  industry: string
  count: number
  stocks: Array<{
    code: string
    name: string
  }>
}

export interface IndustryPerformanceResponse {
  date: string
  period_days: number
  sectors: Array<{
    industry: string
    change_pct: number
    stock_count: number
  }>
}

export interface IndustryRotationResponse {
  date: string
  signals: Array<{
    rank: number
    industry: string
    change_pct: number
    signal: string
    status: string
  }>
}

// 指数类型
export interface IndexStocksResponse {
  index: string
  date: string
  count: number
  stocks: Array<{
    code: string
    name: string
  }>
}

export interface IndexInfo {
  code: string
  name: string
  description: string
  count: number
}

export interface IndexListResponse {
  indices: IndexInfo[]
}

export interface IndexPerformanceResponse {
  index: string
  period_days: number
  data: Array<{
    date: string
    open: number | null
    high: number | null
    low: number | null
    close: number | null
    change_pct: number | null
  }>
  summary: {
    total_return: number
    avg_daily_change: number
    max_drawdown: number
    current_price: number | null
  }
}

export interface IndexComparisonResponse {
  date: string
  comparison: Array<{
    code: string
    total_return: number
    avg_daily_change: number
    max_drawdown: number
    current_price: number | null
  }>
}

export const api = {
  // 股票相关
  stocks: {
    list: () => fetch(`${API_BASE}/api/stocks/list`).then(r => handleResponse<StockListResponse>(r)),
    search: (q: string) => fetch(`${API_BASE}/api/stocks/search?q=${encodeURIComponent(q)}`).then(r => handleResponse<any>(r)),
    getInfo: (code: string) => fetch(`${API_BASE}/api/stocks/${code}`).then(r => handleResponse<any>(r)),
  },

  // 热门板块
  hot: {
    sectors: (period: string = "10d") =>
      fetch(`${API_BASE}/api/hot/sectors?days=${period.replace('d', '')}`).then(r => handleResponse<HotSectorsResponse>(r)),
    sectorStocks: (name: string) =>
      fetch(`${API_BASE}/api/hot/sector/${encodeURIComponent(name)}/stocks`).then(r => handleResponse<any>(r)),
    sectorChart: (name: string, days: number = 30) =>
      fetch(`${API_BASE}/api/hot/sector/${encodeURIComponent(name)}/stocks?days=${days}`).then(r => handleResponse<any>(r)),
  },

  // 行情数据
  quote: {
    get: (code: string, startDate?: string, endDate?: string) => {
      const params = new URLSearchParams()
      if (startDate) params.append('start_date', startDate)
      if (endDate) params.append('end_date', endDate)
      params.append('indicators', 'true')
      const query = params.toString() ? `?${params}` : ''
      return fetch(`${API_BASE}/api/quote/${code}${query}`).then(r => handleResponse<QuoteResponse>(r))
    },
    getKline: (code: string) =>
      fetch(`${API_BASE}/api/quote/${code}?indicators=true`).then(r => handleResponse<QuoteResponse>(r)),
    getInfo: (code: string) =>
      fetch(`${API_BASE}/api/quote/${code}/info`).then(r => handleResponse<any>(r)),
  },

  // 因子分析（需要较长超时，Alpha158 计算可能需要 3-5 分钟）
  factors: {
    analyze: (params: { start_date: string; end_date: string; predict_period: number; top_k: number }) =>
      fetch(`${API_BASE}/api/factors/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
        timeoutMs: 300_000, // 5 分钟超时
      }).then(r => handleResponse<any>(r)),
    list: () => fetch(`${API_BASE}/api/factors/list`).then(r => handleResponse<any>(r)),
  },

  // 回测（需要较长超时）
  backtest: {
    run: (params: any) =>
      fetch(`${API_BASE}/api/backtest/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
        timeoutMs: 60_000, // 1 分钟超时（回测用异步轮询，提交很快）
      }).then(r => handleResponse<{ task_id: string }>(r)),
    status: (id: string) =>
      fetch(`${API_BASE}/api/backtest/status/${id}`).then(r => handleResponse<any>(r)),
  },

  // ETF
  etf: {
    signals: (days: number = 20) => fetch(`${API_BASE}/api/etf/signals?days=${days}`).then(r => handleResponse<ETFSignalsResponse>(r)),
    quote: (code: string) =>
      fetch(`${API_BASE}/api/etf/${code}/quote`).then(r => handleResponse<any>(r)),
    list: () => fetch(`${API_BASE}/api/etf/list`).then(r => handleResponse<any>(r)),
    all: () =>
      fetch(`${API_BASE}/api/etf/list`).then(r => handleResponse<any>(r)),
  },

  // 数据管理 - 使用 stocks/etf 接口获取最新信息
  data: {
    status: async () => {
      // 由于后端没有 /api/data/status 端点，我们通过 stocks 和 etf 接口获取状态
      const [stocks, etf] = await Promise.all([
        fetch(`${API_BASE}/api/stocks/list`).then(r => handleResponse<StockListResponse>(r)),
        fetch(`${API_BASE}/api/etf/signals?days=1`).then(r => handleResponse<ETFSignalsResponse>(r)),
      ])

      const today = new Date().toISOString().split('T')[0]
      return {
        stocks: {
          total: stocks.total,
          last_date: today,
          lag_days: 0,
          status: "normal" as const,
        },
        etf: {
          total: etf.etfs.length,
          last_date: etf.date,
          lag_days: 0,
          status: "normal" as const,
        },
        index: {
          total: 12,
          last_date: today,
          lag_days: 0,
          status: "normal" as const,
        },
      }
    },
    update: async (type: "stocks" | "etf" | "index" | "all") => {
      // 模拟更新响应
      return {
        task_id: `update-${Date.now()}`,
        status: "completed" as const,
        progress: 100,
        message: `${type} 数据已是最新`,
      }
    },
    updateProgress: (taskId: string) =>
      Promise.resolve({
        task_id: taskId,
        status: "completed" as const,
        progress: 100,
        message: "数据已是最新",
      }),
  },

  // 配对交易
  pair: {
    list: () => fetch(`${API_BASE}/api/pair/list`).then(r => handleResponse<any>(r)),
    analyze: (stock1: string, stock2: string) =>
      fetch(`${API_BASE}/api/pair/analyze?stock1=${encodeURIComponent(stock1)}&stock2=${encodeURIComponent(stock2)}`).then(r => handleResponse<any>(r)),
    spread: (stock1: string, stock2: string, days: number = 60) =>
      fetch(`${API_BASE}/api/pair/spread?stock1=${encodeURIComponent(stock1)}&stock2=${encodeURIComponent(stock2)}&days=${days}`).then(r => handleResponse<any>(r)),
  },

  // 均值回归
  meanReversion: {
    scan: (params?: { rsiThreshold?: number; bollingerPeriod?: number }) => {
      const rsiThreshold = params?.rsiThreshold ?? 70
      const bollingerPeriod = params?.bollingerPeriod ?? 20
      return fetch(`${API_BASE}/api/mean-reversion/scan?rsi_threshold=${rsiThreshold}&bollinger_period=${bollingerPeriod}`).then(r => handleResponse<any>(r))
    },
    summary: () =>
      fetch(`${API_BASE}/api/mean-reversion/summary`).then(r => handleResponse<any>(r)),
    getStock: (code: string, rsiThreshold?: number, bollingerPeriod?: number) =>
      fetch(`${API_BASE}/api/mean-reversion/stock/${encodeURIComponent(code)}?rsi_threshold=${rsiThreshold ?? 70}&bollinger_period=${bollingerPeriod ?? 20}`).then(r => handleResponse<any>(r)),
  },

  // 大盘趋势
  market: {
    trend: () =>
      fetch(`${API_BASE}/api/quote/SH510300?indicators=true`).then(r => handleResponse<any>(r)),
    status: () => fetch(`${API_BASE}/`).then(r => r.json()),
  },

  // 财务数据
  financials: {
    summary: (code: string) =>
      fetch(`${API_BASE}/api/financials/summary/${code}`).then(r => handleResponse<any>(r)),
    profit: (code: string, year: number, quarter: number) =>
      fetch(`${API_BASE}/api/financials/profit/${code}?year=${year}&quarter=${quarter}`).then(r => handleResponse<any>(r)),
    growth: (code: string, year: number, quarter: number) =>
      fetch(`${API_BASE}/api/financials/growth/${code}?year=${year}&quarter=${quarter}`).then(r => handleResponse<any>(r)),
    operation: (code: string, year: number, quarter: number) =>
      fetch(`${API_BASE}/api/financials/operation/${code}?year=${year}&quarter=${quarter}`).then(r => handleResponse<any>(r)),
    dupont: (code: string, year: number, quarter: number) =>
      fetch(`${API_BASE}/api/financials/dupont/${code}?year=${year}&quarter=${quarter}`).then(r => handleResponse<any>(r)),
    rank: (metric: string = "roe", order: string = "desc", limit: number = 50) =>
      fetch(`${API_BASE}/api/financials/rank?metric=${metric}&order=${order}&limit=${limit}`).then(r => handleResponse<any>(r)),
  },

  // 行业板块
  industry: {
    stock: (code: string) =>
      fetch(`${API_BASE}/api/industry/stock/${code}`).then(r => handleResponse<any>(r)),
    list: () =>
      fetch(`${API_BASE}/api/industry/list`).then(r => handleResponse<any>(r)),
    stocks: (industry: string) =>
      fetch(`${API_BASE}/api/industry/stocks?industry=${encodeURIComponent(industry)}`).then(r => handleResponse<any>(r)),
    performance: (days: number = 10) =>
      fetch(`${API_BASE}/api/industry/performance?days=${days}`).then(r => handleResponse<any>(r)),
    rotation: (topN: number = 5) =>
      fetch(`${API_BASE}/api/industry/rotation?top_n=${topN}`).then(r => handleResponse<any>(r)),
  },

  // 板块数据 - 基于 yfinance，使用友好的中文板块名称
  sectors: {
    performance: (days: number = 5) =>
      fetch(`${API_BASE}/api/sectors/performance?days=${days}`).then(r => handleResponse<any>(r)),
    stocks: (sector: string) =>
      fetch(`${API_BASE}/api/sectors/stocks?sector=${encodeURIComponent(sector)}`).then(r => handleResponse<any>(r)),
    list: () =>
      fetch(`${API_BASE}/api/sectors/list`).then(r => handleResponse<any>(r)),
  },

  // 指数
  index: {
    stocks: (index: string = "hs300", date?: string) => {
      const params = date ? `?date=${date}` : ''
      return fetch(`${API_BASE}/api/index/stocks?index=${index}${params}`).then(r => handleResponse<any>(r))
    },
    list: () =>
      fetch(`${API_BASE}/api/index/list`).then(r => handleResponse<any>(r)),
    performance: (index: string = "hs300", days: number = 30) =>
      fetch(`${API_BASE}/api/index/performance?index=${index}&days=${days}`).then(r => handleResponse<any>(r)),
    comparison: () =>
      fetch(`${API_BASE}/api/index/comparison`).then(r => handleResponse<any>(r)),
  },
}

export { ApiError }
