// 首页仪表盘 — 响应式 + 精致视觉
import { useState } from "react"
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
import { Activity, TrendingUp, Database, Flame, Zap, RefreshCw, Star, AlertCircle, BarChart3, ArrowRight } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { ParameterSlider } from "@/components/features/parameter-slider"
import { LineChartComponent } from "@/components/charts/line-chart"

// 策略配置
const strategySliders = [
  { id: "factor", name: "因子策略", value: 40, min: 0, max: 100, step: 5, unit: "%", color: "oklch(0.646 0.222 41.116)", description: "基于 Alpha158 因子选股" },
  { id: "rotation", name: "主题轮动", value: 35, min: 0, max: 100, step: 5, unit: "%", color: "oklch(0.6 0.118 184.704)", description: "行业板块轮动策略" },
  { id: "etf", name: "ETF 配置", value: 25, min: 0, max: 100, step: 5, unit: "%", color: "oklch(0.398 0.07 227.392)", description: "行业 ETF 轮动配置" },
]

function average(values: number[]) {
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function buildMarketTrend(data: Array<{ date: string; close: number | null }>) {
  const closes = data.map((item) => item.close ?? 0)
  return data
    .filter((item) => item.close !== null)
    .map((item, index) => {
      const ma60Start = Math.max(0, index - 59)
      const ma200Start = Math.max(0, index - 199)
      return {
        date: item.date,
        value: item.close ?? 0,
        ma60: average(closes.slice(ma60Start, index + 1)),
        ma200: average(closes.slice(ma200Start, index + 1)),
      }
    })
}

export function DashboardPage() {
  const [strategies, setStrategies] = useState(strategySliders)

  const { data: stocksData } = useQuery({
    queryKey: ["stocks", "list"],
    queryFn: () => api.stocks.list(),
  })

  const { data: etfData } = useQuery({
    queryKey: ["etf", "signals"],
    queryFn: () => api.etf.signals(20),
    refetchInterval: 60000,
  })

  const { data: sectorsData } = useQuery({
    queryKey: ["hot-sectors"],
    queryFn: () => api.hot.sectors(),
  })

  const { data: marketPerformance } = useQuery({
    queryKey: ["index", "performance", "hs300", 260],
    queryFn: () => api.index.performance("hs300", 260),
    refetchInterval: 300000,
  })

  const { data: indexComparison } = useQuery({
    queryKey: ["index", "comparison"],
    queryFn: () => api.index.comparison(),
    refetchInterval: 300000,
  })

  const { data: dashboardData } = useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: () => api.dashboard.summary(),
    refetchInterval: 120000,
  })

  const stocksCount = stocksData?.total || 0
  const etfCount = etfData?.etfs?.length || 0
  const sectorsCount = sectorsData?.sectors?.length || 0
  const marketTrend = marketPerformance?.data?.length
    ? buildMarketTrend(marketPerformance.data)
    : []

  const latestTrend = marketTrend[marketTrend.length - 1]
  const marketStatus = {
    trend: latestTrend?.value > latestTrend?.ma200 ? "bullish" : "bearish",
    position: latestTrend?.value > latestTrend?.ma60 ? "高仓位(70-80%)" : "低仓位(30-40%)",
    advice: latestTrend?.value > latestTrend?.ma200 ? "趋势向上，建议积极参与" : "趋势向下，建议谨慎观望",
  }

  const handleStrategyChange = (id: string, value: number) => {
    setStrategies((prev) =>
      prev.map((s) => (s.id === id ? { ...s, value } : s))
    )
  }

  const totalCapital = 1000000
  const strategyAllocation = strategies.map((s) => ({
    ...s,
    amount: Math.round((totalCapital * s.value) / 100),
  }))

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight">仪表盘</h1>
        <p className="text-xs md:text-sm text-muted-foreground">Qlib 量化分析平台概览</p>
      </div>

      {/* 统计卡片 — 移动端 2 列，桌面端 5 列 */}
      <div className="grid gap-3 grid-cols-2 sm:gap-4 lg:grid-cols-5">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-0 gap-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">股票总数</CardTitle>
            <Database className="size-3.5 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-xl md:text-2xl font-bold tracking-tight">{stocksCount}</div>
            <p className="text-[11px] text-muted-foreground mt-0.5">覆盖 A 股</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-0 gap-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">板块数量</CardTitle>
            <TrendingUp className="size-3.5 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-xl md:text-2xl font-bold tracking-tight">{sectorsCount || 28}</div>
            <p className="text-[11px] text-muted-foreground mt-0.5">申万行业</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-0 gap-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">ETF 数量</CardTitle>
            <Activity className="size-3.5 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-xl md:text-2xl font-bold tracking-tight">{etfCount || 320}</div>
            <p className="text-[11px] text-muted-foreground mt-0.5">全市场 ETF</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-0 gap-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">大盘趋势</CardTitle>
            <BarChart3 className={`size-3.5 ${marketStatus.trend === "bullish" ? "text-up" : "text-down"}`} />
          </CardHeader>
          <CardContent>
            <div className={`text-xl md:text-2xl font-bold tracking-tight ${marketStatus.trend === "bullish" ? "text-up" : "text-down"}`}>
              {marketStatus.trend === "bullish" ? "多头" : "空头"}
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              沪深300: {latestTrend?.value?.toFixed(0)}
            </p>
          </CardContent>
        </Card>

        <Card className="col-span-2 lg:col-span-1">
          <CardHeader className="flex flex-row items-center justify-between pb-0 gap-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">建议仓位</CardTitle>
            <AlertCircle className="size-3.5 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-xl md:text-2xl font-bold tracking-tight">{marketStatus.position}</div>
            <p className="text-[11px] text-muted-foreground mt-0.5">基于 MA200/MA60</p>
          </CardContent>
        </Card>
      </div>

      {/* 主内容区 — 移动端单列 */}
      <div className="grid gap-4 md:gap-6 lg:grid-cols-3">
        {/* 策略组合配置 */}
        <div className="lg:col-span-1 space-y-4 md:space-y-6">
          <ParameterSlider
            title="多策略组合配置"
            description="调整各策略的资金分配比例"
            sliders={strategies}
            onChange={handleStrategyChange}
            totalLabel="配置总计"
          />

          <Card>
            <CardHeader>
              <CardTitle>资金分配详情</CardTitle>
              <CardDescription>假设本金 100 万</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2.5">
                {strategyAllocation.map((s) => (
                  <div key={s.id} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <div
                        className="size-2 rounded-full shrink-0"
                        style={{ backgroundColor: s.color }}
                      />
                      <span>{s.name}</span>
                    </div>
                    <span className="font-medium tabular-nums text-muted-foreground">¥{(s.amount / 10000).toFixed(1)}万</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* 大盘趋势图 + 信号 */}
        <div className="lg:col-span-2 space-y-4 md:space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>大盘趋势</CardTitle>
              <CardDescription>
                沪深300 + MA200 + MA60
                {latestTrend?.date && ` • 最新: ${latestTrend.date}`}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <LineChartComponent
                data={marketTrend}
                lines={[
                  { dataKey: "value", name: "沪深300", color: "var(--color-primary)" },
                  { dataKey: "ma200", name: "MA200", color: "var(--color-up)" },
                  { dataKey: "ma60", name: "MA60", color: "var(--color-down)" },
                ]}
                xKey="date"
                height={220}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Star className="size-3.5 text-muted-foreground" />
                本周策略信号汇总
              </CardTitle>
              <CardDescription>各策略当前信号与操作建议</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {(dashboardData?.strategy_signals || []).map((s: any) => (
                  <div key={s.strategy} className="flex items-center justify-between p-2.5 rounded-lg bg-muted/40">
                    <div className="flex items-center gap-2.5">
                      <div className="w-0.5 h-5 rounded-full bg-foreground/40" />
                      <div className="space-y-0.5">
                        <p className="text-sm font-medium">{s.strategy}</p>
                        <p className="text-[11px] text-muted-foreground">{s.reason}</p>
                      </div>
                    </div>
                    <div className="text-right flex flex-col items-end gap-1">
                      <Badge variant={s.signal === "持有" ? "outline" : "default"} className="text-[11px] px-1.5 py-0">
                        {s.signal}
                      </Badge>
                      <p className="text-[11px] text-muted-foreground">{s.stocks_count} 只标的</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* ETF 行情 */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <div className="space-y-0.5">
              <CardTitle className="flex items-center gap-2">
                <RefreshCw className="size-3.5 text-muted-foreground" />
                今日行业 ETF 行情
              </CardTitle>
              <CardDescription>
                主要行业 ETF 实时行情与信号
                {etfData?.date && ` • 更新: ${etfData.date}`}
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" className="shrink-0" onClick={() => window.location.reload()}>
              <RefreshCw className="size-3" />
              刷新
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {/* 桌面端表格 */}
          <div className="hidden md:block">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>ETF 名称</TableHead>
                  <TableHead>代码</TableHead>
                  <TableHead className="text-right">净值</TableHead>
                  <TableHead className="text-right">涨跌幅</TableHead>
                  <TableHead>信号</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(etfData?.etfs || []).slice(0, 8).map((etf: any) => {
                  const price = etf.price ?? 1
                  const change = etf.change_pct ?? etf.change ?? 0
                  const signal = etf.signal ?? "hold"
                  return (
                    <TableRow key={etf.code}>
                      <TableCell className="font-medium text-sm">{etf.name}</TableCell>
                      <TableCell className="font-mono text-muted-foreground text-xs">{etf.code}</TableCell>
                      <TableCell className="text-right tabular-nums text-sm">{typeof price === "number" ? price.toFixed(3) : "--"}</TableCell>
                      <TableCell className={`text-right tabular-nums text-sm font-medium ${change >= 0 ? "text-up" : "text-down"}`}>
                        {change >= 0 ? "+" : ""}{typeof change === "number" ? change.toFixed(2) : "0"}%
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={signal === "buy" ? "default" : signal === "sell" ? "destructive" : "outline"}
                          className="text-[11px]"
                        >
                          {signal === "buy" ? "买入" : signal === "sell" ? "规避" : signal === "hold" ? "持有" : signal}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <a href={`/quote?code=${etf.code}`} className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-0.5 transition-colors">
                          详情 <ArrowRight className="size-2.5" />
                        </a>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>

          {/* 移动端卡片列表 */}
          <div className="md:hidden space-y-2">
            {(etfData?.etfs || []).slice(0, 6).map((etf: any) => {
              const price = etf.price ?? 1
              const change = etf.change_pct ?? etf.change ?? 0
              return (
                <a key={etf.code} href={`/quote?code=${etf.code}`} className="block">
                  <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30 hover:bg-muted/60 transition-colors">
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{etf.name}</p>
                      <p className="text-[11px] text-muted-foreground font-mono">{etf.code}</p>
                    </div>
                    <div className="text-right shrink-0 ml-3">
                      <p className="text-sm font-medium tabular-nums">{typeof price === "number" ? price.toFixed(3) : "--"}</p>
                      <p className={`text-xs tabular-nums font-medium ${change >= 0 ? "text-up" : "text-down"}`}>
                        {change >= 0 ? "+" : ""}{typeof change === "number" ? change.toFixed(2) : "0"}%
                      </p>
                    </div>
                  </div>
                </a>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* 指数对比 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="size-3.5 text-muted-foreground" />
            主要指数表现对比
          </CardTitle>
          <CardDescription>
            沪深300、上证50、中证500 近期表现对比
            {indexComparison?.date && ` • 更新: ${indexComparison.date}`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 grid-cols-1 sm:grid-cols-3">
            {(indexComparison?.comparison || []).map((index: any) => {
              const indexNames: Record<string, string> = {
                "hs300": "沪深300",
                "sz50": "上证50",
                "zz500": "中证500"
              }
              const name = indexNames[index.code] || index.code
              return (
                <div key={index.code} className="rounded-lg bg-muted/40 p-4 space-y-2.5">
                  <p className="text-sm font-medium">{name}</p>
                  <div className="flex items-baseline justify-between">
                    <span className="text-xs text-muted-foreground">区间收益</span>
                    <span className={`text-lg font-bold tabular-nums ${index.total_return >= 0 ? "text-up" : "text-down"}`}>
                      {index.total_return >= 0 ? "+" : ""}{index.total_return}%
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-y-1.5 text-xs">
                    <span className="text-muted-foreground">日均</span>
                    <span className={`text-right tabular-nums ${index.avg_daily_change >= 0 ? "text-up" : "text-down"}`}>
                      {index.avg_daily_change >= 0 ? "+" : ""}{index.avg_daily_change}%
                    </span>
                    <span className="text-muted-foreground">回撤</span>
                    <span className="text-right text-down tabular-nums">{index.max_drawdown}%</span>
                    <span className="text-muted-foreground">点位</span>
                    <span className="text-right font-medium tabular-nums">{index.current_price?.toFixed(2) || "--"}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* 快速链接 */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        {[
          { href: "/hot-sectors", icon: Flame, label: "主题热点", desc: "行业板块涨跌幅排行" },
          { href: "/quote", icon: TrendingUp, label: "行情分析", desc: "K线图与技术指标" },
          { href: "/backtest", icon: Zap, label: "模型回测", desc: "LightGBM 策略回测" },
          { href: "/etf-rotation", icon: RefreshCw, label: "ETF 轮动", desc: "行业 ETF 轮动信号" },
        ].map((item) => (
          <a key={item.href} href={item.href} className="group">
            <Card className="transition-all duration-200 hover:shadow-[var(--shadow-card-hover)] hover:border-primary/20 group-hover:bg-accent/20 h-full">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <item.icon className="size-3.5 text-muted-foreground" />
                  {item.label}
                </CardTitle>
                <CardDescription>{item.desc}</CardDescription>
              </CardHeader>
            </Card>
          </a>
        ))}
      </div>

      {/* 欢迎信息 */}
      <Card className="bg-muted/20">
        <CardContent className="py-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground text-sm">Qlib 量化分析平台</span>
            <span className="hidden sm:inline text-muted-foreground/40">|</span>
            <span>数据来源: Qlib + yfinance</span>
            <span className="hidden sm:inline text-muted-foreground/40">|</span>
            <span className="font-medium text-foreground">{marketStatus.advice}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
