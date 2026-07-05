// 侧边栏导航组件 — 响应式 + 无边框分隔
import { useLocation, useNavigate } from "react-router-dom"
import {
  Home,
  Flame,
  TrendingUp,
  Microscope,
  Zap,
  TrendingDown,
  Link2,
  RefreshCw,
  Target,
  Database,
  Shield,
  PieChart,
  Globe,
  Newspaper,
  Bot,
  MessageSquare,
  Brain,
  Layers,
  ListChecks,
  Settings,
  MonitorCog,
  Calculator,
  Swords,
  FlaskConical,
  ChevronLeft,
  ChevronRight,
  X,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useAppStore } from "@/stores/app-store"

const NAVIGATION_ITEMS = [
  { icon: Home, label: "首页", path: "/" },
  { icon: Flame, label: "主题热点", path: "/hot-sectors" },
  { icon: TrendingUp, label: "行情分析", path: "/quote" },
  { icon: Microscope, label: "因子分析", path: "/factors" },
  { icon: Zap, label: "模型回测", path: "/backtest" },
  { icon: TrendingDown, label: "均值回归", path: "/mean-reversion" },
  { icon: Link2, label: "配对交易", path: "/pair-trading" },
  { icon: RefreshCw, label: "ETF轮动", path: "/etf-rotation" },
  { icon: Target, label: "ETF筛选", path: "/etf-screener" },
  { icon: Database, label: "数据管理", path: "/data-management" },
  { icon: Shield, label: "风险管理", path: "/risk" },
  { icon: PieChart, label: "组合优化", path: "/portfolio" },
  { icon: Globe, label: "宏观策略", path: "/macro-dashboard" },
  { icon: Newspaper, label: "新闻分析", path: "/news-analysis" },
  { icon: Bot, label: "AI 策略", path: "/ai-strategy" },
  { icon: MessageSquare, label: "智能体辩论", path: "/agent-debate" },
  { icon: Brain, label: "深度学习", path: "/dl-models" },
  { icon: Layers, label: "智能股票池", path: "/stock-pool" },
  { icon: ListChecks, label: "盘后选股", path: "/screening-workflow" },
  { icon: Calculator, label: "交易计划", path: "/trade-plan" },
  { icon: Swords, label: "龙虎榜", path: "/dragon-tiger" },
  { icon: FlaskConical, label: "实验看板", path: "/experiments" },
  { icon: MonitorCog, label: "系统状态", path: "/system-status" },
  { icon: Settings, label: "LLM 设置", path: "/settings" },
]

export function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { sidebarOpen, toggleSidebar } = useAppStore()

  const handleNavigate = (path: string) => {
    navigate(path)
    // 移动端导航后自动关闭侧边栏
    if (window.innerWidth < 768) {
      toggleSidebar()
    }
  }

  return (
    <>
      {/* 移动端遮罩层 */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[2px] md:hidden"
          onClick={toggleSidebar}
        />
      )}

      <aside
        className={cn(
          // 桌面端: 固定侧边栏，背景色差异分隔，无 border-r
          "fixed md:relative z-50 md:z-auto",
          "flex flex-col bg-card md:bg-card transition-all duration-300 ease-in-out",
          // 桌面端: 始终显示
          "md:flex",
          // 移动端: 滑入滑出
          sidebarOpen
            ? "translate-x-0"
            : "-translate-x-full md:translate-x-0",
          sidebarOpen ? "w-64" : "w-64 md:w-16",
          // 高度适配
          "h-screen md:h-auto",
          // 移动端阴影
          "shadow-lg md:shadow-none"
        )}
      >
        {/* Logo */}
        <div className="flex h-14 items-center justify-between px-4 shrink-0">
          {(sidebarOpen || window.innerWidth >= 768) && (
            <div className="flex items-center gap-2.5 overflow-hidden">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary">
                <TrendingUp className="h-4 w-4 text-primary-foreground" />
              </div>
              <span className={cn(
                "text-sm font-bold tracking-tight whitespace-nowrap transition-all duration-300",
                !sidebarOpen && "md:hidden"
              )}>
                Qlib 量化
              </span>
            </div>
          )}
          <button
            onClick={toggleSidebar}
            className={cn(
              "flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
              sidebarOpen && "-mr-2"
            )}
          >
            {sidebarOpen ? (
              <ChevronLeft className="h-4 w-4 hidden md:block" />
            ) : (
              <ChevronRight className="h-4 w-4 hidden md:block" />
            )}
            <X className="h-4 w-4 md:hidden" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-2 py-1">
          <ul className="space-y-0.5">
            {NAVIGATION_ITEMS.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path

              return (
                <li key={item.path}>
                  <button
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-accent text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground",
                      // 折叠状态下居中图标
                      !sidebarOpen && "md:justify-center md:px-0"
                    )}
                    onClick={() => handleNavigate(item.path)}
                    title={!sidebarOpen ? item.label : undefined}
                  >
                    <Icon className="size-4 shrink-0" />
                    <span className={cn(
                      "whitespace-nowrap transition-all duration-300",
                      !sidebarOpen && "md:hidden"
                    )}>
                      {item.label}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </nav>

        {/* Footer */}
        <div className={cn(
          "px-4 py-3 shrink-0 transition-all duration-300 overflow-hidden",
          !sidebarOpen && "md:hidden"
        )}>
          <div className="border-t border-border/60 pt-3">
            <p className="text-[11px] text-muted-foreground">Qlib 量化平台 v3.0</p>
          </div>
        </div>
      </aside>
    </>
  )
}
