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
    ],
  },
])

// 创建 React Query 客户端
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
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
