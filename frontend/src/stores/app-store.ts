// 全局状态管理
import { create } from "zustand"
import { persist } from "zustand/middleware"

// ── 页面参数持久化类型 ──
export interface BacktestParams {
  model: string
  trainStart: string
  trainEnd: string
  testStart: string
  testEnd: string
  topK: string
  rebalance: string
  commission: string
  slippage: string
  singlePosition: string
  stopLoss: string
}

export interface FactorParams {
  startDate: string
  endDate: string
  predictPeriod: number
  topK: number
  neutralize: string
  selectedFactors: string[]
  activeTab: string
}

interface AppState {
  // 侧边栏状态
  sidebarOpen: boolean
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void

  // 主题状态
  theme: "light" | "dark"
  toggleTheme: () => void
  setTheme: (theme: "light" | "dark") => void

  // 搜索状态
  searchQuery: string
  setSearchQuery: (query: string) => void

  // ── 风险管理页面状态 ──
  riskCodes: string[]
  riskInputValue: string
  setRiskCodes: (codes: string[], inputValue: string) => void

  // ── 回测页面状态 ──
  backtestParams: BacktestParams
  backtestActiveTab: string
  setBacktestParams: (params: BacktestParams) => void
  setBacktestActiveTab: (tab: string) => void

  // ── 因子分析页面状态 ──
  factorParams: FactorParams
  setFactorParams: (params: Partial<FactorParams>) => void

  // ── 投资组合页面状态 ──
  portfolioCodes: string
  setPortfolioCodes: (codes: string) => void
}

// 默认值
const DEFAULT_BACKTEST_PARAMS: BacktestParams = {
  model: "lightgbm",
  trainStart: "2023-01-01",
  trainEnd: "2024-06-30",
  testStart: "2024-07-01",
  testEnd: "2024-12-31",
  topK: "30",
  rebalance: "5",
  commission: "0.0003",
  slippage: "0.0003",
  singlePosition: "0.05",
  stopLoss: "-0.08",
}

const DEFAULT_FACTOR_PARAMS: FactorParams = {
  startDate: "2026-01-01",
  endDate: "2026-04-30",
  predictPeriod: 5,
  topK: 20,
  neutralize: "",
  selectedFactors: [],
  activeTab: "overview",
}

const DEFAULT_RISK_CODES = ["600519.SS", "000858.SZ", "601318.SS", "000333.SZ", "600036.SS", "601012.SS", "300750.SZ", "000002.SZ"]

const DEFAULT_PORTFOLIO_CODES = "600519.SS 000858.SZ 601318.SS 000333.SZ 600036.SS"

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // 侧边栏
      sidebarOpen: true,
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),

      // 主题
      theme: "light",
      toggleTheme: () => set((state) => {
        const newTheme = state.theme === "light" ? "dark" : "light"
        if (newTheme === "dark") {
          document.documentElement.classList.add("dark")
        } else {
          document.documentElement.classList.remove("dark")
        }
        return { theme: newTheme }
      }),
      setTheme: (theme) => set(() => {
        if (theme === "dark") {
          document.documentElement.classList.add("dark")
        } else {
          document.documentElement.classList.remove("dark")
        }
        return { theme }
      }),

      // 搜索
      searchQuery: "",
      setSearchQuery: (query) => set({ searchQuery: query }),

      // 风险管理
      riskCodes: DEFAULT_RISK_CODES,
      riskInputValue: DEFAULT_RISK_CODES.join(" "),
      setRiskCodes: (codes, inputValue) => set({ riskCodes: codes, riskInputValue: inputValue }),

      // 回测
      backtestParams: DEFAULT_BACKTEST_PARAMS,
      backtestActiveTab: "config",
      setBacktestParams: (params) => set({ backtestParams: params }),
      setBacktestActiveTab: (tab) => set({ backtestActiveTab: tab }),

      // 因子分析
      factorParams: DEFAULT_FACTOR_PARAMS,
      setFactorParams: (params) => set((state) => ({
        factorParams: { ...state.factorParams, ...params },
      })),

      // 投资组合
      portfolioCodes: DEFAULT_PORTFOLIO_CODES,
      setPortfolioCodes: (codes) => set({ portfolioCodes: codes }),
    }),
    {
      name: "qlib-app-store",
      partialize: (state) => ({
        theme: state.theme,
        sidebarOpen: state.sidebarOpen,
        // 持久化页面状态
        riskCodes: state.riskCodes,
        riskInputValue: state.riskInputValue,
        backtestParams: state.backtestParams,
        backtestActiveTab: state.backtestActiveTab,
        factorParams: state.factorParams,
        portfolioCodes: state.portfolioCodes,
      }),
    }
  )
)

// 初始化主题
if (typeof window !== "undefined") {
  const storedTheme = localStorage.getItem("qlib-app-store")
  if (storedTheme) {
    try {
      const parsed = JSON.parse(storedTheme)
      if (parsed.state?.theme === "dark") {
        document.documentElement.classList.add("dark")
      }
    } catch {
      // ignore
    }
  }
}
