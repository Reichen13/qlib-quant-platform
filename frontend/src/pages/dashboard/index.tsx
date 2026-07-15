// 首页仪表盘 — 决策导向：今晚焦点 + 快捷入口
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  TrendingUp,
  Database,
  Flame,
  Zap,
  RefreshCw,
  AlertCircle,
  ArrowRight,
  Crosshair,
  ListChecks,
  Layers,
} from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { api } from "@/lib/api"

function formatSignedPercent(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value >= 0 ? "+" : ""}${value}%`
    : "--"
}

function trendClass(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "text-muted-foreground"
  }
  return value >= 0 ? "text-up" : "text-down"
}

function verdictTone(verdict: string | undefined) {
  if (!verdict) return "secondary"
  if (verdict.includes("止损") || verdict.includes("深度")) return "destructive"
  if (verdict.includes("浮盈")) return "default"
  if (verdict.includes("浮亏") || verdict.includes("微亏")) return "secondary"
  return "outline"
}

const quickLinks = [
  { href: "/screening-workflow", icon: ListChecks, label: "盘后选股", desc: "生成今晚候选并落库" },
  { href: "/stock-pool", icon: Layers, label: "智能股票池", desc: "刷新核心候选池" },
  { href: "/quote", icon: TrendingUp, label: "行情分析", desc: "K 线与技术指标" },
  { href: "/backtest", icon: Zap, label: "模型回测", desc: "净收益与调仓口径回测" },
  { href: "/hot-sectors", icon: Flame, label: "主题热点", desc: "板块强弱参考" },
  { href: "/data-management", icon: Database, label: "数据管理", desc: "健康检查与更新" },
]

export function DashboardPage() {
  const navigate = useNavigate()

  const {
    data: focusData,
    isLoading: focusLoading,
    isFetching: focusFetching,
    refetch: refetchFocus,
    isError: focusError,
    error: focusErrorObj,
  } = useQuery({
    queryKey: ["dashboard", "focus"],
    queryFn: () => api.dashboard.focus(),
    refetchInterval: 120000,
  })

  const buyableTop3 = Array.isArray(focusData?.buyable_top3) ? focusData.buyable_top3 : []
  const holdings = Array.isArray(focusData?.holdings) ? focusData.holdings : []
  const tradingAllowed = focusData?.trading_allowed !== false
  const circuitActive = Boolean(focusData?.circuit_breaker?.active)
  const trustTrusted = focusData?.data_trust?.trusted
  const buyableSource = focusData?.buyable_source
  const sourceLabel =
    buyableSource?.source === "screening_history"
      ? `盘后落库 · ${buyableSource.run_date || "--"}`
      : buyableSource?.source === "screening_task"
        ? "盘后任务结果"
        : "暂无盘后记录"

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight">仪表盘</h1>
        <p className="text-xs md:text-sm text-muted-foreground">
          决策入口：今晚看什么、持仓怎么办；大盘装饰与假信号已收敛
        </p>
      </div>

      {/* 今晚焦点 */}
      <Card className="border-primary/20 bg-gradient-to-br from-primary/5 via-background to-background">
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between pb-2">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base md:text-lg">
              <Crosshair className="size-4 text-primary" />
              今晚焦点
            </CardTitle>
            <CardDescription>
              盘后可买 Top3 + 持仓复核 · {sourceLabel}
              {focusData?.updated_at
                ? ` · 更新 ${String(focusData.updated_at).slice(0, 19).replace("T", " ")}`
                : ""}
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetchFocus()}
              disabled={focusFetching}
            >
              <RefreshCw className={`mr-1.5 size-3.5 ${focusFetching ? "animate-spin" : ""}`} />
              刷新
            </Button>
            <Button size="sm" onClick={() => navigate("/screening-workflow")}>
              <ListChecks className="mr-1.5 size-3.5" />
              去盘后选股
              <ArrowRight className="ml-1 size-3.5" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {(circuitActive || trustTrusted === false || !tradingAllowed) && (
            <div className="space-y-2">
              {circuitActive && (
                <div className="flex items-start gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-300">
                  <AlertCircle className="mt-0.5 size-4 shrink-0" />
                  <span>
                    {focusData?.circuit_breaker?.message ||
                      "熔断：近3期 T+5 胜率偏低，暂停展示新开仓精选"}
                  </span>
                </div>
              )}
              {trustTrusted === false && (
                <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-200">
                  <AlertCircle className="mt-0.5 size-4 shrink-0" />
                  <span>
                    {focusData?.data_trust?.message ||
                      "本地数据尾部复权不可信，已隐藏买入精选"}
                  </span>
                </div>
              )}
              {!tradingAllowed && !circuitActive && trustTrusted !== false && (
                <div className="rounded-md border border-muted bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
                  当前不允许新开仓信号展示
                </div>
              )}
            </div>
          )}

          {focusError && (
            <div className="text-sm text-red-600 dark:text-red-400">
              焦点加载失败：
              {focusErrorObj instanceof Error
                ? focusErrorObj.message
                : "请检查后端 /api/dashboard/focus"}
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">今晚可看 · 可买 Top 3</p>
                <Badge variant={tradingAllowed && buyableTop3.length ? "default" : "secondary"}>
                  {tradingAllowed ? `${buyableTop3.length} 只` : "已关闭"}
                </Badge>
              </div>
              {focusLoading ? (
                <p className="text-sm text-muted-foreground py-6 text-center">加载中…</p>
              ) : buyableTop3.length === 0 ? (
                <div className="rounded-lg border border-dashed bg-muted/30 px-3 py-6 text-center text-sm text-muted-foreground">
                  {circuitActive || trustTrusted === false
                    ? "因熔断或数据状态，暂不展示买入精选"
                    : "暂无盘后可买记录。请先运行「盘后选股」并确保有 buyable 结果落库。"}
                </div>
              ) : (
                <div className="space-y-2">
                  {buyableTop3.map((item: any, idx: number) => (
                    <div
                      key={item.code || idx}
                      className="flex items-start gap-3 rounded-lg border bg-card/80 p-3"
                    >
                      <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                        {idx + 1}
                      </div>
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium truncate">
                            {item.name || item.code}
                          </span>
                          <span className="text-xs text-muted-foreground tabular-nums">
                            {item.code}
                          </span>
                          {typeof item.score === "number" && (
                            <Badge variant="outline" className="text-[10px]">
                              分 {item.score.toFixed?.(2) ?? item.score}
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground line-clamp-2">
                          {item.reason || item.verdict_reason || "盘后筛选可买候选"}
                        </p>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="shrink-0 text-xs"
                        onClick={() =>
                          navigate(`/quote?code=${encodeURIComponent(item.code || "")}`)
                        }
                      >
                        行情
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">持仓复核</p>
                <Badge variant="outline">{holdings.length} 只</Badge>
              </div>
              {focusLoading ? (
                <p className="text-sm text-muted-foreground py-6 text-center">加载中…</p>
              ) : holdings.length === 0 ? (
                <div className="rounded-lg border border-dashed bg-muted/30 px-3 py-6 text-center text-sm text-muted-foreground">
                  暂无持仓记录。录入持仓后这里显示止损与浮盈状态。
                </div>
              ) : (
                <div className="rounded-lg border overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>标的</TableHead>
                        <TableHead className="text-right">现价</TableHead>
                        <TableHead className="text-right">盈亏</TableHead>
                        <TableHead>判定</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {holdings.slice(0, 8).map((h: any) => (
                        <TableRow key={h.code}>
                          <TableCell>
                            <div className="font-medium text-sm">{h.name || h.code}</div>
                            <div className="text-[11px] text-muted-foreground">{h.code}</div>
                          </TableCell>
                          <TableCell className="text-right tabular-nums text-sm">
                            {h.current_price != null ? h.current_price : "--"}
                          </TableCell>
                          <TableCell
                            className={`text-right tabular-nums text-sm ${trendClass(h.pnl_pct)}`}
                          >
                            {formatSignedPercent(
                              typeof h.pnl_pct === "number"
                                ? Number(h.pnl_pct.toFixed(2))
                                : h.pnl_pct
                            )}
                          </TableCell>
                          <TableCell>
                            <Badge variant={verdictTone(h.verdict) as any} className="text-[10px]">
                              {h.verdict || "--"}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 决策相关快捷入口 */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-3">
        {quickLinks.map((item) => (
          <button
            key={item.href}
            type="button"
            onClick={() => navigate(item.href)}
            className="group text-left"
          >
            <Card className="h-full transition-all duration-200 hover:shadow-[var(--shadow-card-hover)] hover:border-primary/20 group-hover:bg-accent/20">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <item.icon className="size-3.5 text-muted-foreground" />
                  {item.label}
                </CardTitle>
                <CardDescription>{item.desc}</CardDescription>
              </CardHeader>
            </Card>
          </button>
        ))}
      </div>
    </div>
  )
}
