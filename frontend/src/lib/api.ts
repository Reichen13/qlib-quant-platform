// API 客户端封装
// 开发环境用 localhost，生产环境用相对路径（由 Nginx 代理）
const API_BASE = import.meta.env.DEV ? "http://localhost:8001" : ""
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

  // 注入服务器管理 Key 和 LLM Base URL（如果已配置）。
  // LLM API Key 只通过相关请求体传递，避免误当作服务器管理 Key。
  const apiKey = localStorage.getItem("qlib-admin-api-key")
  const baseUrl = localStorage.getItem("qlib-llm-base-url")
  const headers = { ...(requestInit.headers as Record<string, string> || {}) }
  if (apiKey) {
    headers["X-API-Key"] = apiKey
  }
  if (baseUrl) {
    headers["X-LLM-Base-URL"] = baseUrl
  }

  try {
    return await globalThis.fetch(input, {
      ...requestInit,
      headers,
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

function parseErrorMessage(status: number, body: string): string {
  let detail = body
  try {
    const parsed = JSON.parse(body)
    if (typeof parsed?.detail === "string") {
      detail = parsed.detail
    } else if (typeof parsed?.message === "string") {
      detail = parsed.message
    }
  } catch {
    // Keep raw text body when the server did not return JSON.
  }

  if (status === 401 || status === 403) {
    if (detail.includes("API Key") || detail.includes("X-API-Key")) {
      return `服务器管理 Key 未配置或不正确：${detail}`
    }
  }

  if (status === 504 || detail.includes("Gateway Time-out") || detail.includes("504")) {
    return "服务器处理超时。因子分析这类计算较重，建议后台提交后等待结果，或先缩短日期范围再试。"
  }

  return detail || "Unknown error"
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.text().catch(() => "Unknown error")
    throw new ApiError(response.status, parseErrorMessage(response.status, error))
  }
  return response.json()
}

 // 缓存服务器 LLM 配置状态，避免每次请求都查询
 let _serverLlmConfigured: boolean | null = null
 
 async function checkServerLlmConfigured(): Promise<boolean> {
   if (_serverLlmConfigured !== null) return _serverLlmConfigured
   try {
     const resp = await globalThis.fetch(`${API_BASE}/api/llm/status`)
     const data = await resp.json()
     _serverLlmConfigured = !!data?.server_configured
   } catch {
     _serverLlmConfigured = false
   }
   return _serverLlmConfigured
 }
 
 async function getLlmRequestConfig() {
   // 如果服务器已配置 LLM，不传本地 key，让后端使用服务器配置
   const serverReady = await checkServerLlmConfigured()
   if (serverReady) return { apiKey: "", baseUrl: "", quickModel: "", deepModel: "" }
 
   const storedConfig = (() => {
     try {
       const raw = localStorage.getItem("qlib-app-store")
       if (!raw) return {}
       const parsed = JSON.parse(raw)
       return parsed?.state || {}
     } catch {
       return {}
     }
   })()
 
   return {
     apiKey: localStorage.getItem("qlib-api-key") || storedConfig.llmApiKey || "",
     baseUrl: localStorage.getItem("qlib-llm-base-url") || storedConfig.llmBaseUrl || "",
     quickModel: localStorage.getItem("qlib-llm-quick-model") || storedConfig.llmQuickModel || "",
     deepModel: localStorage.getItem("qlib-llm-deep-model") || storedConfig.llmDeepModel || "",
   }
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

export interface TurtleTradeCandidate {
  code: string
  name?: string
  entry_price?: number | null
  atr?: number | null
  target_price?: number | null
  source?: string
}

export interface TurtleTradePlanRequest {
  account_equity: number
  risk_percent: number
  max_units?: number
  atr_period?: number
  min_reward_risk?: number
  candidates: TurtleTradeCandidate[]
}

export interface TurtleTradePlan {
  code: string
  name: string
  method: string
  direction: string
  account_equity: number
  risk_percent: number
  risk_budget: number
  entry_price: number
  atr: number
  n_value: number
  stop_distance: number
  initial_stop: number
  unit_shares: number
  unit_position_value: number
  planned_unit_risk: number
  max_units: number
  max_shares: number
  max_position_value: number
  add_on_prices: number[]
  target_price?: number | null
  reward_risk_ratio?: number | null
  min_reward_risk: number
  verdict: string
  warnings: string[]
  plan_text: string
  source: string
  data_status: string
}

export interface TurtleTradePlanResponse {
  method: string
  account_equity: number
  risk_percent: number
  total: number
  plans: TurtleTradePlan[]
  errors: Array<{ code: string; message: string }>
  disclaimer: string
}

export interface ScreeningCandidate {
  code: string
  name: string
  price?: number | null
  change_pct?: number | null
  action: string
  bucket: string
  reason: string
  mean_reversion?: {
    rsi?: number | null
    bollingerPosition?: number | null
    signal?: string
    strength?: string
    price?: number | null
  }
  factor_signal?: {
    score?: number | null
    rank?: number | null
    matched_factors?: number | null
    top_factor_count?: number | null
    as_of?: string
    source?: string
  }
  ai_strategy?: {
    status?: string
    score?: number | null
    recommendation?: string
    action?: string
    reason?: string
    votes?: Array<Record<string, any>>
    cautions?: string[]
  }
  agent?: {
    status?: string
    rating?: string
    risk_level?: string
  }
  warning?: string
}

export interface ScreeningRunRequest {
  candidates?: string[]
  include_llm?: boolean
  risk_start_date?: string
  risk_end_date?: string
  generated_strategy?: Record<string, any>
}

export interface ScreeningRunResponse {
  run_date: string
  data_health: Record<string, any>
  hot_sectors: Array<Record<string, any>>
  etf_signals: Array<Record<string, any>>
  pair_signals: Array<Record<string, any>>
  risk_summary: Record<string, any>
  factor_summary: Record<string, any>
  ai_strategy_summary: Record<string, any>
  candidates: ScreeningCandidate[]
  buckets: Record<string, ScreeningCandidate[]>
  llm_review: Record<string, any>
  warnings: string[]
}

// 因子 IC 类型
export interface FactorIC {
  factor: string
  ic: number
  rank_ic: number
  icir: number
  category?: string
  skewness?: number | null
  kurtosis?: number | null
  t_statistic?: number | null
  p_value?: number | null
  information_ratio?: number | null
  ic_autocorr?: number | null
  industry_contribution?: Record<string, number> | null
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
  priceAdjustment?: {
    status: "normal" | "warning" | "error"
    adjustment_mode: string
    factor_field_status: string
    message: string
    sample_size?: number
    all_one_factor_count?: number
    non_one_factor_count?: number
    possible_unadjusted_jump_count?: number
    suspect_examples?: Array<Record<string, any>>
    warnings?: string[]
    source_policy?: Record<string, any>
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
  net_total_return?: number
  annual_return?: number
  net_annual_return?: number
  sharpe_ratio?: number
  calmar_ratio?: number
  max_drawdown?: number
  win_rate?: number
  profit_loss_ratio?: number
  t_statistic?: number
  p_value?: number
  information_ratio?: number
  sortino_ratio?: number
  monthly_win_rate?: number
  equity?: Array<{ date: string; value: number; benchmark: number }>
  net_equity?: Array<{ date: string; value: number; benchmark: number }>
  drawdown?: Array<{ date: string; value: number }>
  top_buys?: Array<{ code: string; name: string; score: number; reason: string }>
  top_sells?: Array<{ code: string; name: string; score: number; reason: string }>
  position_advice?: string
  constraint_analysis?: {
    original_universe?: number
    valid_universe?: number
    excluded_chi_next_star?: number
    excluded_codes_sample?: string[]
    limit_up_hits_estimated?: number
    limit_down_hits_estimated?: number
    suspension_days_estimated?: number
    suspended_stocks_estimated?: number
    constraints_active?: string[]
    warning?: string
  }
  factor_source?: string
  attribution?: {
    allocation_effect: number
    selection_effect: number
    interaction_effect: number
    total_active_return: number
    by_industry?: Record<string, { allocation: number; selection: number }>
  }
  attribution_curve?: Array<{
    date: string
    allocation: number
    selection: number
    interaction: number
    total_active: number
  }>
  attribution_interpretation?: string
  cost_impact_estimate?: string
  cumulative_cost?: number
  price_adjustment_note?: string
  warnings?: string[]
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

export interface DataLogEntry {
  type: string
  title: string
  detail: string
  time: string
}

export interface DataLogsResponse {
  logs: DataLogEntry[]
  checked_at: string
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
    getKline: (code: string, frequency: "daily" | "weekly" | "monthly" = "daily") =>
      fetch(`${API_BASE}/api/quote/${code}?frequency=${frequency}&indicators=true`).then(r => handleResponse<QuoteResponse>(r)),
    getInfo: (code: string) =>
      fetch(`${API_BASE}/api/quote/${code}/info`).then(r => handleResponse<any>(r)),
  },

  // 因子分析（需要较长超时，Alpha158 计算可能需要 3-5 分钟）
  factors: {
    analyze: (params: { start_date: string; end_date: string; predict_period: number; top_k: number; neutralize?: string }) =>
      fetch(`${API_BASE}/api/factors/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
        timeoutMs: 300_000, // 5 分钟超时
      }).then(r => handleResponse<any>(r)),
    submitAnalysis: (params: { start_date: string; end_date: string; predict_period: number; top_k: number; neutralize?: string }) =>
      fetch(`${API_BASE}/api/factors/analyze/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
        timeoutMs: 60_000,
      }).then(r => handleResponse<{ task_id: string; status: string; progress?: number; message?: string }>(r)),
    analysisStatus: (taskId: string) =>
      fetch(`${API_BASE}/api/factors/analyze/status/${taskId}`, {
        timeoutMs: 30_000,
      }).then(r => handleResponse<any>(r)),
    list: () => fetch(`${API_BASE}/api/factors/list`).then(r => handleResponse<any>(r)),
    decay: (params: { start_date: string; end_date: string; predict_period: number; top_k: number }) =>
      fetch(`${API_BASE}/api/factors/decay`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
        timeoutMs: 300_000,
      }).then(r => handleResponse<any>(r)),
    correlation: (params: { start_date: string; end_date: string; predict_period: number; top_k: number }) =>
      fetch(`${API_BASE}/api/factors/correlation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
        timeoutMs: 120_000,
      }).then(r => handleResponse<any>(r)),
    combine: (params: { start_date: string; end_date: string; predict_period: number; top_k: number }) =>
      fetch(`${API_BASE}/api/factors/combine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
        timeoutMs: 120_000,
      }).then(r => handleResponse<any>(r)),
    detail: (factorName: string, startDate: string, endDate: string, predictPeriod: number = 5) =>
      fetch(`${API_BASE}/api/factors/${encodeURIComponent(factorName)}/detail?start_date=${startDate}&end_date=${endDate}&predict_period=${predictPeriod}`)
        .then(r => handleResponse<any>(r)),
    quantileReturns: (factorName: string, startDate: string, endDate: string, predictPeriod: number = 5, numQuantiles: number = 5) =>
      fetch(`${API_BASE}/api/factors/${encodeURIComponent(factorName)}/quantile-returns?start_date=${startDate}&end_date=${endDate}&predict_period=${predictPeriod}&num_quantiles=${numQuantiles}`)
        .then(r => handleResponse<any>(r)),
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
    reportUrl: (id: string) => `${API_BASE}/api/backtest/report/${encodeURIComponent(id)}.md`,
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

  // 盘后选股工作流
  screening: {
    run: (params?: ScreeningRunRequest) =>
      fetch(`${API_BASE}/api/screening/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params || {}),
        timeoutMs: 120_000,
      }).then(r => handleResponse<ScreeningRunResponse>(r)),
  },

  // 数据管理
  data: {
    status: async () => {
      const health = await fetch(`${API_BASE}/api/data/health`, { timeoutMs: 30_000 }).then(r => handleResponse<any>(r))
      const src = health.sources
      return {
        stocks: src.stocks,
        etf: src.stocks.etf,
        index: src.stocks.index,
        priceAdjustment: src.price_adjustment,
      }
    },
    logs: () =>
      fetch(`${API_BASE}/api/data/logs`, { timeoutMs: 30_000 }).then(r => handleResponse<DataLogsResponse>(r)),
    freshness: () =>
      fetch(`${API_BASE}/api/data/freshness`, { timeoutMs: 30_000 }).then(r => handleResponse<any>(r)),
    update: async (
      type: "stocks" | "core" | "etf" | "index" | "all",
      options?: { rebuildStale?: boolean; overwriteExisting?: boolean; codes?: string[]; startDate?: string; endDate?: string },
    ) =>
      fetch(`${API_BASE}/api/data/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type,
          rebuild_stale: options?.rebuildStale ?? false,
          overwrite_existing: options?.overwriteExisting ?? false,
          codes: options?.codes && options.codes.length > 0 ? options.codes : undefined,
          start_date: options?.startDate,
          end_date: options?.endDate,
        }),
        timeoutMs: 30_000,
      }).then(r => handleResponse<DataUpdateResponse>(r)),
    updateProgress: (taskId: string) =>
      fetch(`${API_BASE}/api/data/update/${taskId}`).then(r => handleResponse<DataUpdateResponse>(r)),
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
      fetch(`${API_BASE}/api/index/performance?index=${index}&days=${days}`, { timeoutMs: 30_000 }).then(r => handleResponse<any>(r)),
    comparison: () =>
      fetch(`${API_BASE}/api/index/comparison`, { timeoutMs: 30_000 }).then(r => handleResponse<any>(r)),
  },

  // 风险管理
  risk: {
    analyze: (params: { codes: string[]; start_date?: string; end_date?: string }) =>
      fetch(`${API_BASE}/api/risk/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
        timeoutMs: 30_000,
      }).then(r => handleResponse<any>(r)),
    stressTest: (params: { codes: string[]; start_date?: string; end_date?: string }) =>
      fetch(`${API_BASE}/api/risk/stress-test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
        timeoutMs: 30_000,
      }).then(r => handleResponse<any>(r)),
    dailyChecklist: () =>
      fetch(`${API_BASE}/api/risk/daily-checklist`).then(r => handleResponse<any>(r)),
  },

  // 投资组合优化
  portfolio: {
    optimize: (params: { codes: string[]; start_date?: string; end_date?: string; method: string; max_weight: number; turnover_lambda?: number }) =>
      fetch(`${API_BASE}/api/portfolio/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
        timeoutMs: 30_000,
      }).then(r => handleResponse<any>(r)),
  },

  // 首页仪表盘汇总
  dashboard: {
    summary: () =>
      fetch(`${API_BASE}/api/dashboard/summary`).then(r => handleResponse<any>(r)),
  },

  // 宏观策略
  macro: {
    indicators: () =>
      fetch(`${API_BASE}/api/macro/indicators`, { timeoutMs: 60_000 }).then(r => handleResponse<any>(r)),
    regime: (indicators: Record<string, number>) =>
      fetch(`${API_BASE}/api/macro/regime`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ indicators }),
        timeoutMs: 60_000,
      }).then(r => handleResponse<any>(r)),
    allocation: (indicators: Record<string, number>) =>
      fetch(`${API_BASE}/api/macro/allocation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ indicators }),
        timeoutMs: 60_000,
      }).then(r => handleResponse<any>(r)),
    history: (months: number = 12) =>
      fetch(`${API_BASE}/api/macro/history?months=${months}`, { timeoutMs: 60_000 }).then(r => handleResponse<any>(r)),
  },

  // 新闻分析
  news: {
    sentiment: (code: string, days: number = 7) =>
      fetch(`${API_BASE}/api/news/sentiment/${encodeURIComponent(code)}?days=${days}`).then(r => handleResponse<any>(r)),
     dailyBrief: async () => {
     const { apiKey, baseUrl, quickModel, deepModel } = await getLlmRequestConfig()
      const params = new URLSearchParams()
      if (apiKey) params.append("api_key", apiKey)
      if (baseUrl) params.append("base_url", baseUrl)
      if (quickModel) params.append("quick_model", quickModel)
      if (deepModel) params.append("deep_model", deepModel)
      const qs = params.toString()
      return fetch(`${API_BASE}/api/news/daily-brief${qs ? "?" + qs : ""}`).then(r => handleResponse<any>(r))
    },
    events: (code: string, days: number = 30) =>
      fetch(`${API_BASE}/api/news/events/${encodeURIComponent(code)}?days=${days}`).then(r => handleResponse<any>(r)),
    marketSentiment: () =>
      fetch(`${API_BASE}/api/news/market-sentiment`).then(r => handleResponse<any>(r)),
  },

  // AI 策略
  aiStrategy: {
    templates: () =>
      fetch(`${API_BASE}/api/ai-strategy/templates`).then(r => handleResponse<any>(r)),
     generate: async (description: string, useDeep: boolean = false) => {
      const { apiKey, baseUrl, quickModel, deepModel } = await getLlmRequestConfig()
      return fetch(`${API_BASE}/api/ai-strategy/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description,
          use_deep: useDeep,
          api_key: apiKey || undefined,
          base_url: baseUrl || undefined,
          quick_model: quickModel || undefined,
          deep_model: deepModel || undefined,
        }),
        timeoutMs: 120_000,
      }).then(r => handleResponse<any>(r))
    },
     analyze: async (holdings: { code: string; name: string; weight: number; cost?: number }[], totalCapital?: number, riskTolerance?: string) => {
      const { apiKey, baseUrl, quickModel, deepModel } = await getLlmRequestConfig()
      return fetch(`${API_BASE}/api/ai-strategy/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          holdings,
          total_capital: totalCapital || 1_000_000,
          risk_tolerance: riskTolerance || "moderate",
          api_key: apiKey || undefined,
          base_url: baseUrl || undefined,
          quick_model: quickModel || undefined,
          deep_model: deepModel || undefined,
        }),
        timeoutMs: 120_000,
      }).then(r => handleResponse<any>(r))
    },
     optimize: async (strategyType: string, paramRanges?: Record<string, any>) => {
      const { apiKey, baseUrl, quickModel, deepModel } = await getLlmRequestConfig()
      return fetch(`${API_BASE}/api/ai-strategy/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_type: strategyType,
          param_ranges: paramRanges || {},
          api_key: apiKey || undefined,
          base_url: baseUrl || undefined,
          quick_model: quickModel || undefined,
          deep_model: deepModel || undefined,
        }),
        timeoutMs: 120_000,
      }).then(r => handleResponse<any>(r))
    },
    screeningSignals: (candidates?: string[]) =>
      fetch(`${API_BASE}/api/ai-strategy/screening-signals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidates: candidates && candidates.length > 0 ? candidates : undefined }),
        timeoutMs: 120_000,
      }).then(r => handleResponse<any>(r)),
  },

  // 多智能体辩论
  agent: {
     analyze: async (code: string, asyncMode: boolean = true) => {
      const { apiKey, baseUrl, quickModel, deepModel } = await getLlmRequestConfig()
      return fetch(`${API_BASE}/api/agent/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code,
          async_mode: asyncMode,
          api_key: apiKey || undefined,
          base_url: baseUrl || undefined,
          quick_model: quickModel || undefined,
          deep_model: deepModel || undefined,
        }),
        timeoutMs: 30_000,
      }).then(r => handleResponse<any>(r))
    },
    report: (taskId: string) =>
      fetch(`${API_BASE}/api/agent/report/${taskId}`).then(r => handleResponse<any>(r)),
    memory: (code: string) =>
      fetch(`${API_BASE}/api/agent/memory/${encodeURIComponent(code)}`).then(r => handleResponse<any>(r)),
  },

  // 深度学习模型
  dlModels: {
    list: () =>
      fetch(`${API_BASE}/api/dl-models/list`).then(r => handleResponse<any>(r)),
    train: (modelName: string, config?: Record<string, any>) =>
      fetch(`${API_BASE}/api/dl-models/train?model_name=${encodeURIComponent(modelName)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config || {}),
      }).then(r => handleResponse<any>(r)),
    status: (taskId: string) =>
      fetch(`${API_BASE}/api/dl-models/status/${taskId}`).then(r => handleResponse<any>(r)),
  },

  // 智能股票池
  stockPool: {
    list: () =>
      fetch(`${API_BASE}/api/stock-pool/list`).then(r => handleResponse<any>(r)),
    create: (definition: any) =>
      fetch(`${API_BASE}/api/stock-pool/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(definition),
      }).then(r => handleResponse<any>(r)),
    get: (id: string) =>
      fetch(`${API_BASE}/api/stock-pool/${id}`).then(r => handleResponse<any>(r)),
    refresh: (id: string) =>
      fetch(`${API_BASE}/api/stock-pool/${id}/refresh`, {
        method: "POST",
      }).then(r => handleResponse<any>(r)),
    delete: (id: string) =>
      fetch(`${API_BASE}/api/stock-pool/${id}`, {
        method: "DELETE",
      }).then(r => handleResponse<any>(r)),
  },

  system: {
    environment: () => fetch(`${API_BASE}/api/system/environment`).then(r => handleResponse<any>(r)),
    tasks: () => fetch(`${API_BASE}/api/system/tasks`).then(r => handleResponse<any>(r)),
  },

  tradePlan: {
    turtle: (params: TurtleTradePlanRequest) =>
      fetch(`${API_BASE}/api/trade-plan/turtle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
        timeoutMs: 60_000,
      }).then(r => handleResponse<TurtleTradePlanResponse>(r)),
  },

  // LLM 配置
  llm: {
    testConnection: (apiKey: string, baseUrl?: string, quickModel?: string, deepModel?: string) =>
      fetch(`${API_BASE}/api/llm/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: apiKey,
          base_url: baseUrl || "",
          quick_model: quickModel || "",
          deep_model: deepModel || "",
        }),
        timeoutMs: 60_000,
      }).then(r => handleResponse<any>(r)),
    status: () =>
      fetch(`${API_BASE}/api/llm/status`).then(r => handleResponse<any>(r)),
  },
}

export { ApiError }
