// API 类型定义

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

export interface Sector {
  name: string
  change_pct: number
  volume: number
  stock_count: number
}

export interface HotSectorsResponse {
  date: string
  sectors: Sector[]
}

export interface QuoteData {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number
  pct_chg?: number
}

export interface QuoteResponse {
  code: string
  name: string
  data: QuoteData[]
  indicators?: {
    ma5?: number[]
    ma10?: number[]
    ma20?: number[]
    ma60?: number[]
    rsi?: number[]
    macd?: {
      dif?: number[]
      dea?: number[]
      histogram?: number[]
    }
  }
}

export interface BacktestParams {
  train_start: string
  train_end: string
  test_start: string
  test_end: string
  topk: number
  n_drop: number
}

export interface BacktestStatusResponse {
  id: string
  status: "pending" | "running" | "completed" | "failed"
  progress?: number
  result?: {
    sharpe: number
    annual_return: number
    max_drawdown: number
    win_rate: number
  }
  error?: string
}

export interface ETFInfo {
  code: string
  name: string
  price: number
  change_pct: number
  signal: "buy" | "hold" | "sell"
  score: number
}

export interface ETFSignalsResponse {
  date: string
  etfs: ETFInfo[]
}
