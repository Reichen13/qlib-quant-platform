// 全局状态管理
import { create } from "zustand"
import { persist } from "zustand/middleware"
import { relativeDate } from "@/lib/utils"

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
  sourceFactor: string
}

export interface PersistedBacktestResult {
  task_id: string
  status: "running" | "completed" | "failed"
  progress?: number
  error?: string
  [key: string]: unknown
}

export interface FactorParams {
  startDate: string
  endDate: string
  predictPeriod: number
  topK: number
  neutralize: string
  selectedFactors: string[]
  activeTab: string
  selectedCategory: string
  sortBy: "ic" | "rankIC"
  selectedFactor: string | null
  detailTab: "ic_stability" | "factor_series" | "industry_contrib" | "quantile_returns"
  showDecay: boolean
  showCombination: boolean
  showAdvancedStats: boolean
  analysisTaskId: string | null
}

export interface QuoteParams {
  selectedStock: string
  timeframe: "daily" | "weekly" | "monthly"
  showMA: boolean
  showBollinger: boolean
  showVolume: boolean
}

export interface EtfScreenerParams {
  searchQuery: string
  selectedCategory: string
  sortBy: string
  filters: {
    minPe: string
    maxPe: string
    minSize: string
  }
  dataSource: "core" | "all"
}

export interface DataUpdateStep {
  id: string
  name: string
  status: "pending" | "running" | "completed" | "failed"
  progress: number
  message?: string
  startTime?: string
  endTime?: string
}

export interface DataManagementParams {
  updateTaskId: string | null
  isUpdating: boolean
  updateSteps: DataUpdateStep[]
  overallProgress: number
}

export interface AgentDebateParams {
  code: string
  agentDebateTaskId: string | null
  status: "idle" | "running" | "completed" | "failed" | "error"
  report: unknown | null
  activeStage: number
  memory: string
}

export interface AiStrategyParams {
  activeTab: "generate" | "analyze" | "optimize" | "templates"
  nlInput: string
  useDeep: boolean
  generated: unknown | null
  holdingsInput: string
  analysis: unknown | null
  optimizeStrategy: string
  optimizeResult: unknown | null
}

export interface PortfolioParams {
  method: string
  maxWeight: number
  turnoverLambda: number
}

export interface MeanReversionParams {
  searchQuery: string
  rsiThreshold: string
  bollingerPeriod: string
  scanType: "both" | "rsi" | "bollinger"
  activeTab: "overbought" | "oversold" | "watch"
}

export interface DlModelsParams {
  trainingModelId: string | null
  trainingTaskId: string | null
  trainResult: unknown | null
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
  backtestTaskId: string | null
  backtestResult: PersistedBacktestResult | null
  setBacktestParams: (params: BacktestParams) => void
  setBacktestActiveTab: (tab: string) => void
  setBacktestTaskState: (params: { taskId?: string | null; result?: PersistedBacktestResult | null }) => void

  // ── 因子分析页面状态 ──
  factorParams: FactorParams
  setFactorParams: (params: Partial<FactorParams>) => void

  quoteParams: QuoteParams
  setQuoteParams: (params: Partial<QuoteParams>) => void

  etfScreenerParams: EtfScreenerParams
  setEtfScreenerParams: (params: Partial<Omit<EtfScreenerParams, "filters">> & {
    filters?: Partial<EtfScreenerParams["filters"]>
  }) => void

  dataManagementParams: DataManagementParams
  setDataManagementParams: (params: Partial<DataManagementParams>) => void

  agentDebateParams: AgentDebateParams
  setAgentDebateParams: (params: Partial<AgentDebateParams>) => void

  aiStrategyParams: AiStrategyParams
  setAiStrategyParams: (params: Partial<AiStrategyParams>) => void

  // ── 投资组合页面状态 ──
  portfolioParams: PortfolioParams
  portfolioCodes: string
  setPortfolioParams: (params: Partial<PortfolioParams>) => void
  setPortfolioCodes: (codes: string) => void

  meanReversionParams: MeanReversionParams
  setMeanReversionParams: (params: Partial<MeanReversionParams>) => void

  dlModelsParams: DlModelsParams
  setDlModelsParams: (params: Partial<DlModelsParams>) => void

  // ── LLM 设置页面状态 ──
  llmApiKey: string
  llmBaseUrl: string
  llmQuickModel: string
  llmDeepModel: string
  setLlmApiKey: (key: string) => void
  setLlmBaseUrl: (url: string) => void
  setLlmQuickModel: (model: string) => void
  setLlmDeepModel: (model: string) => void
}

// 动态默认值工厂函数
function createDefaultBacktestParams(): BacktestParams {
  return {
    model: "lightgbm",
    trainStart: relativeDate({ months: -24 }),
    trainEnd: relativeDate({ months: -7 }),
    testStart: relativeDate({ months: -6 }),
    testEnd: relativeDate({ days: -1 }),
    topK: "30",
    rebalance: "5",
    commission: "0.0003",
    slippage: "0.0003",
    singlePosition: "0.05",
    stopLoss: "-0.08",
    sourceFactor: "",
  }
}

function createDefaultFactorParams(): FactorParams {
  return {
    startDate: relativeDate({ months: -6 }),
    endDate: relativeDate({ days: -1 }),
    predictPeriod: 5,
    topK: 20,
    neutralize: "none",
    selectedFactors: [],
    activeTab: "overview",
    selectedCategory: "全部",
    sortBy: "ic",
    selectedFactor: null,
    detailTab: "ic_stability",
    showDecay: false,
    showCombination: false,
    showAdvancedStats: false,
    analysisTaskId: null,
  }
}

function createDefaultQuoteParams(): QuoteParams {
  return {
    selectedStock: "SH600519",
    timeframe: "daily",
    showMA: true,
    showBollinger: true,
    showVolume: true,
  }
}

function createDefaultEtfScreenerParams(): EtfScreenerParams {
  return {
    searchQuery: "",
    selectedCategory: "全部",
    sortBy: "change-desc",
    filters: { minPe: "", maxPe: "", minSize: "" },
    dataSource: "core",
  }
}

function createDefaultDataManagementParams(): DataManagementParams {
  return {
    updateTaskId: null,
    isUpdating: false,
    updateSteps: [],
    overallProgress: 0,
  }
}

function createDefaultAgentDebateParams(): AgentDebateParams {
  return {
    code: "",
    agentDebateTaskId: null,
    status: "idle",
    report: null,
    activeStage: 0,
    memory: "",
  }
}

function createDefaultAiStrategyParams(): AiStrategyParams {
  return {
    activeTab: "generate",
    nlInput: "",
    useDeep: false,
    generated: null,
    holdingsInput: "",
    analysis: null,
    optimizeStrategy: "",
    optimizeResult: null,
  }
}

function createDefaultPortfolioParams(): PortfolioParams {
  return {
    method: "max_sharpe",
    maxWeight: 30,
    turnoverLambda: 0,
  }
}

function createDefaultMeanReversionParams(): MeanReversionParams {
  return {
    searchQuery: "",
    rsiThreshold: "70",
    bollingerPeriod: "20",
    scanType: "both",
    activeTab: "overbought",
  }
}

function createDefaultDlModelsParams(): DlModelsParams {
  return {
    trainingModelId: null,
    trainingTaskId: null,
    trainResult: null,
  }
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
      backtestParams: createDefaultBacktestParams(),
      backtestActiveTab: "config",
      backtestTaskId: null,
      backtestResult: null,
      setBacktestParams: (params) => set({ backtestParams: params }),
      setBacktestActiveTab: (tab) => set({ backtestActiveTab: tab }),
      setBacktestTaskState: ({ taskId, result }) => set((state) => ({
        backtestTaskId: taskId !== undefined ? taskId : state.backtestTaskId,
        backtestResult: result !== undefined ? result : state.backtestResult,
      })),

      // 因子分析
      factorParams: createDefaultFactorParams(),
      setFactorParams: (params) => set((state) => ({
        factorParams: { ...state.factorParams, ...params },
      })),

      quoteParams: createDefaultQuoteParams(),
      setQuoteParams: (params) => set((state) => ({
        quoteParams: { ...state.quoteParams, ...params },
      })),

      etfScreenerParams: createDefaultEtfScreenerParams(),
      setEtfScreenerParams: (params) => set((state) => ({
        etfScreenerParams: {
          ...state.etfScreenerParams,
          ...params,
          filters: params.filters
            ? { ...state.etfScreenerParams.filters, ...params.filters }
            : state.etfScreenerParams.filters,
        },
      })),

      dataManagementParams: createDefaultDataManagementParams(),
      setDataManagementParams: (params) => set((state) => ({
        dataManagementParams: { ...state.dataManagementParams, ...params },
      })),

      agentDebateParams: createDefaultAgentDebateParams(),
      setAgentDebateParams: (params) => set((state) => ({
        agentDebateParams: { ...state.agentDebateParams, ...params },
      })),

      // 投资组合
      aiStrategyParams: createDefaultAiStrategyParams(),
      setAiStrategyParams: (params) => set((state) => ({
        aiStrategyParams: { ...state.aiStrategyParams, ...params },
      })),

      portfolioParams: createDefaultPortfolioParams(),
      portfolioCodes: DEFAULT_PORTFOLIO_CODES,
      setPortfolioParams: (params) => set((state) => ({
        portfolioParams: { ...state.portfolioParams, ...params },
      })),
      setPortfolioCodes: (codes) => set({ portfolioCodes: codes }),

      // LLM 设置
      meanReversionParams: createDefaultMeanReversionParams(),
      setMeanReversionParams: (params) => set((state) => ({
        meanReversionParams: { ...state.meanReversionParams, ...params },
      })),

      dlModelsParams: createDefaultDlModelsParams(),
      setDlModelsParams: (params) => set((state) => ({
        dlModelsParams: { ...state.dlModelsParams, ...params },
      })),

      llmApiKey: "",
      llmBaseUrl: "",
      llmQuickModel: "",
      llmDeepModel: "",
      setLlmApiKey: (key) => set({ llmApiKey: key }),
      setLlmBaseUrl: (url) => set({ llmBaseUrl: url }),
      setLlmQuickModel: (model) => set({ llmQuickModel: model }),
      setLlmDeepModel: (model) => set({ llmDeepModel: model }),
    }),
    {
      name: "qlib-app-store",
      merge: (persisted, current) => {
        const persistedState = persisted as Partial<AppState> | undefined
        return {
          ...current,
          ...persistedState,
          quoteParams: {
            ...current.quoteParams,
            ...persistedState?.quoteParams,
          },
          factorParams: {
            ...current.factorParams,
            ...persistedState?.factorParams,
          },
          backtestParams: {
            ...current.backtestParams,
            ...persistedState?.backtestParams,
          },
          backtestTaskId: persistedState?.backtestTaskId ?? current.backtestTaskId,
          backtestResult: persistedState?.backtestResult ?? current.backtestResult,
          etfScreenerParams: {
            ...current.etfScreenerParams,
            ...persistedState?.etfScreenerParams,
            filters: {
              ...current.etfScreenerParams.filters,
              ...persistedState?.etfScreenerParams?.filters,
            },
          },
          dataManagementParams: {
            ...current.dataManagementParams,
            ...persistedState?.dataManagementParams,
          },
          agentDebateParams: {
            ...current.agentDebateParams,
            ...persistedState?.agentDebateParams,
          },
          aiStrategyParams: {
            ...current.aiStrategyParams,
            ...persistedState?.aiStrategyParams,
          },
          portfolioParams: {
            ...current.portfolioParams,
            ...persistedState?.portfolioParams,
          },
          meanReversionParams: {
            ...current.meanReversionParams,
            ...persistedState?.meanReversionParams,
          },
          dlModelsParams: {
            ...current.dlModelsParams,
            ...persistedState?.dlModelsParams,
          },
        }
      },
      partialize: (state) => ({
        theme: state.theme,
        sidebarOpen: state.sidebarOpen,
        // 持久化页面状态
        riskCodes: state.riskCodes,
        riskInputValue: state.riskInputValue,
        backtestParams: state.backtestParams,
        backtestActiveTab: state.backtestActiveTab,
        backtestTaskId: state.backtestTaskId,
        backtestResult: state.backtestResult,
        factorParams: state.factorParams,
        quoteParams: state.quoteParams,
        etfScreenerParams: state.etfScreenerParams,
        dataManagementParams: state.dataManagementParams,
        agentDebateParams: state.agentDebateParams,
        aiStrategyParams: state.aiStrategyParams,
        portfolioParams: state.portfolioParams,
        portfolioCodes: state.portfolioCodes,
        meanReversionParams: state.meanReversionParams,
        dlModelsParams: state.dlModelsParams,
        // 持久化 LLM 设置
        llmApiKey: state.llmApiKey,
        llmBaseUrl: state.llmBaseUrl,
        llmQuickModel: state.llmQuickModel,
        llmDeepModel: state.llmDeepModel,
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
