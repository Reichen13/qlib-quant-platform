import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createBrowserRouter } from "react-router-dom"
import { MainLayout } from "./components/layout/main-layout"
import { DashboardPage } from "./pages/dashboard"
import { HotSectorsPage } from "./pages/hot-sectors"
import { QuoteAnalysisPage } from "./pages/quote"
import { FactorAnalysisPage } from "./pages/factors"
import { BacktestPage } from "./pages/backtest"
import { MeanReversionPage } from "./pages/mean-reversion"
import { PairTradingPage } from "./pages/pair-trading"
import { EtfRotationPage } from "./pages/etf-rotation"
import { EtfScreenerPage } from "./pages/etf-screener"
import { DataManagementPage } from "./pages/data-management"
import { RiskPage } from "./pages/risk"
import { PortfolioPage } from "./pages/portfolio"
import { MacroDashboardPage } from "./pages/macro-dashboard"
import { NewsAnalysisPage } from "./pages/news-analysis"
import { AiStrategyPage } from "./pages/ai-strategy"
import { AgentDebatePage } from "./pages/agent-debate"
import { DlModelsPage } from "./pages/dl-models"
import { StockPoolPage } from "./pages/stock-pool"

// 创建路由
const router = createBrowserRouter([
  {
    path: "/",
    element: <MainLayout />,
    children: [
      {
        index: true,
        element: <DashboardPage />,
      },
      {
        path: "hot-sectors",
        element: <HotSectorsPage />,
      },
      {
        path: "quote",
        element: <QuoteAnalysisPage />,
      },
      {
        path: "factors",
        element: <FactorAnalysisPage />,
      },
      {
        path: "backtest",
        element: <BacktestPage />,
      },
      {
        path: "mean-reversion",
        element: <MeanReversionPage />,
      },
      {
        path: "pair-trading",
        element: <PairTradingPage />,
      },
      {
        path: "etf-rotation",
        element: <EtfRotationPage />,
      },
      {
        path: "etf-screener",
        element: <EtfScreenerPage />,
      },
      {
        path: "data-management",
        element: <DataManagementPage />,
      },
      {
        path: "risk",
        element: <RiskPage />,
      },
      {
        path: "portfolio",
        element: <PortfolioPage />,
      },
      {
        path: "macro-dashboard",
        element: <MacroDashboardPage />,
      },
      {
        path: "news-analysis",
        element: <NewsAnalysisPage />,
      },
      {
        path: "ai-strategy",
        element: <AiStrategyPage />,
      },
      {
        path: "agent-debate",
        element: <AgentDebatePage />,
      },
      {
        path: "dl-models",
        element: <DlModelsPage />,
      },
      {
        path: "stock-pool",
        element: <StockPoolPage />,
      },
    ],
  },
])

// 创建 React Query 客户端
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 60 * 1000, // 1分钟内不重新请求，减少页面切换时的重复加载
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

export default App
