// 投资组合优化器 - Man Group 风格组合构建系统
import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { PieChart, Loader2, AlertTriangle, X, BarChart3 } from "lucide-react"
import { LineChartComponent } from "@/components/charts/line-chart"
import { BarChart } from "@/components/charts/bar-chart"
import { InstructionsPanel } from "@/components/features/instructions-panel"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"

const DEFAULT_CODES = ["600519.SS", "000858.SZ", "601318.SS", "000333.SZ", "600036.SS", "601012.SS", "300750.SZ", "000002.SZ"]

const METHODS = [
  { value: "max_sharpe", label: "最大夏普比率", desc: "Max Sharpe Ratio - 收益/风险最优化" },
  { value: "min_variance", label: "最小方差", desc: "Minimum Variance - 风险最小化" },
  { value: "risk_parity", label: "风险平价", desc: "Risk Parity - 各资产风险贡献相等" },
  { value: "equal_weight", label: "等权配置", desc: "Equal Weight - 基准对照" },
]

export function PortfolioPage() {
  const [codes, setCodes] = useState<string[]>(DEFAULT_CODES)
  const [inputValue, setInputValue] = useState(DEFAULT_CODES.join(" "))
  const [method, setMethod] = useState("max_sharpe")
  const [maxWeight, setMaxWeight] = useState(30)
  const [optimizeEnabled, setOptimizeEnabled] = useState(false)

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["portfolio", "optimize", codes, method, maxWeight],
    queryFn: () => api.portfolio.optimize({
      codes,
      method,
      max_weight: maxWeight / 100,
    }),
    enabled: optimizeEnabled && codes.length >= 2,
    retry: 1,
  })

  const handleOptimize = () => {
    const parsedCodes = inputValue
      .split(/[\s,]+/)
      .map(s => s.trim())
      .filter(Boolean)
    if (parsedCodes.length < 2) return
    setCodes(parsedCodes)
    setOptimizeEnabled(true)
    setTimeout(() => refetch(), 0)
  }

  const handleRemoveCode = (code: string) => {
    const newCodes = codes.filter(c => c !== code)
    setCodes(newCodes)
    setInputValue(newCodes.join(" "))
  }

  const formatPct = (val: number | undefined) => {
    if (val === undefined || val === null) return "--"
    return `${(val * 100).toFixed(2)}%`
  }

  const weights = data?.weights || []
  const bench = data?.benchmark
  const frontier = data?.efficient_frontier || []

  // 有效前沿数据转换 - 使用 ret 字段
  const frontierData = frontier.map((p: any) => ({
    volatility: p.volatility,
    ret: p.ret,
    sharpe: p.sharpe,
    label: `σ=${(p.volatility * 100).toFixed(1)}%`,
  }))

  // 优化组合点
  const optimalPoint = data ? {
    volatility: data.expected_volatility,
    ret: data.expected_return,
  } : null

  // 权重柱状图数据
  const weightChartData = weights.map((w: any) => ({
    name: w.code?.split(".")[0] || w.code,
    weight: (w.weight * 100),
  }))

  // 找到最高收益、最低风险组合供参考
  const maxRetPoint = frontierData.length > 0
    ? frontierData.reduce((a: any, b: any) => a.ret > b.ret ? a : b)
    : null
  const minVolPoint = frontierData.length > 0
    ? frontierData.reduce((a: any, b: any) => a.volatility < b.volatility ? a : b)
    : null

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <PieChart className="size-5 text-muted-foreground" />
          投资组合优化
        </h1>
        <p className="text-muted-foreground">Man Group 风格组合构建系统 - 均值方差 / 风险平价 / 有效前沿</p>
      </div>

      {/* 配置面板 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">优化配置</CardTitle>
          <CardDescription>输入股票代码，选择优化方法</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label className="text-xs">股票代码</Label>
              <div className="flex gap-2">
                <Input
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder="600519.SS 000858.SZ ..."
                  className="flex-1 font-mono text-sm"
                  onKeyDown={(e) => e.key === "Enter" && handleOptimize()}
                />
                <Button onClick={handleOptimize} disabled={isLoading}>
                  {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "优化"}
                </Button>
              </div>
              {codes.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {codes.map(code => (
                    <Badge key={code} variant="secondary" className="gap-1 text-xs">
                      {code}
                      <X className="h-3 w-3 cursor-pointer" onClick={() => handleRemoveCode(code)} />
                    </Badge>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-xs">优化方法</Label>
                <Select value={method} onValueChange={setMethod}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {METHODS.map(m => (
                      <SelectItem key={m.value} value={m.value}>
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {METHODS.find(m => m.value === method)?.desc}
                </p>
              </div>

              <div className="space-y-1.5">
                <div className="flex justify-between">
                  <Label className="text-xs">单票最大权重</Label>
                  <span className="text-xs font-medium">{maxWeight}%</span>
                </div>
                <Slider
                  value={[maxWeight]}
                  onValueChange={([v]) => setMaxWeight(v)}
                  min={5}
                  max={100}
                  step={5}
                />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 加载 / 错误状态 */}
      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" />
          <span className="ml-3 text-muted-foreground">正在优化组合...</span>
        </div>
      )}

      {isError && (
        <Card className="border-down/50 bg-down/5">
          <CardContent className="py-6">
            <div className="flex items-center gap-3 text-down">
              <AlertTriangle className="h-5 w-5" />
              <div>
                <p className="font-medium">优化失败</p>
                <p className="text-sm text-muted-foreground mt-1">
                  {(error as any)?.message || "请检查股票代码是否正确"}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {data && !isLoading && (
        <>
          {/* 核心指标 */}
          <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">预期年化收益</CardTitle>
              </CardHeader>
              <CardContent>
                <div className={`text-xl font-bold ${data.expected_return >= 0 ? "text-up" : "text-down"}`}>
                  {formatPct(data.expected_return)}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">预期波动率</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xl font-bold">{formatPct(data.expected_volatility)}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">夏普比率</CardTitle>
              </CardHeader>
              <CardContent>
                <div className={`text-xl font-bold ${data.sharpe_ratio >= 1 ? "text-up" : ""}`}>
                  {data.sharpe_ratio?.toFixed(2)}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">分散化比率</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xl font-bold">
                  {data.diversification_ratio?.toFixed(2)}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* 有效前沿 + 当前组合 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <BarChart3 className="h-4 w-4" />
                  有效前沿
                </CardTitle>
                <CardDescription>风险-收益权衡曲线，标记点为最优组合</CardDescription>
              </CardHeader>
              <CardContent>
                {frontierData.length > 0 ? (
                  <div className="relative">
                    <LineChartComponent
                      data={frontierData}
                      lines={[{ dataKey: "ret", name: "有效前沿", color: "var(--color-primary)" }]}
                      xKey="volatility"
                      height={350}
                    />
                    {optimalPoint && (
                      <div className="mt-3 flex gap-4 text-xs text-muted-foreground">
                        <span>
                          ★ 最优组合: σ={formatPct(optimalPoint.volatility)}, r={formatPct(optimalPoint.ret)}
                        </span>
                      </div>
                    )}
                    {minVolPoint && maxRetPoint && (
                      <div className="flex gap-4 mt-1 text-xs text-muted-foreground">
                        <span>最小风险: σ={formatPct(minVolPoint.volatility)}</span>
                        <span>最大收益: r={formatPct(maxRetPoint.ret)}</span>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-center py-12 text-muted-foreground">暂无有效前沿数据</p>
                )}
              </CardContent>
            </Card>

            {/* 权重分配 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">最优权重分配</CardTitle>
                <CardDescription>{METHODS.find(m => m.value === method)?.label}</CardDescription>
              </CardHeader>
              <CardContent>
                {weightChartData.length > 0 ? (
                  <div className="space-y-4">
                    <BarChart
                      data={weightChartData}
                      bars={[{ dataKey: "weight", name: "权重 (%)", color: "var(--color-primary)" }]}
                      xKey="name"
                      height={250}
                    />
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>代码</TableHead>
                          <TableHead className="text-right">权重</TableHead>
                          <TableHead className="text-right">仓位条</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {weights
                          .filter((w: any) => w.weight > 0.001)
                          .sort((a: any, b: any) => b.weight - a.weight)
                          .map((w: any) => (
                            <TableRow key={w.code}>
                              <TableCell className="font-mono text-xs">{w.code}</TableCell>
                              <TableCell className="text-right font-medium">
                                {(w.weight * 100).toFixed(1)}%
                              </TableCell>
                              <TableCell className="text-right w-32">
                                <div className="h-2 bg-muted rounded-full overflow-hidden">
                                  <div
                                    className="h-full bg-primary rounded-full"
                                    style={{ width: `${w.weight * 100}%` }}
                                  />
                                </div>
                              </TableCell>
                            </TableRow>
                          ))}
                      </TableBody>
                    </Table>
                  </div>
                ) : (
                  <p className="text-center py-12 text-muted-foreground">暂无权重数据</p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* 基准对比 */}
          {bench && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">基准对比（等权配置）</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
                  <div className="space-y-0.5">
                    <p className="text-xs text-muted-foreground">年化收益</p>
                    <p className={`font-medium ${bench.expected_return >= 0 ? "text-up" : "text-down"}`}>
                      {formatPct(bench.expected_return)}
                    </p>
                  </div>
                  <div className="space-y-0.5">
                    <p className="text-xs text-muted-foreground">波动率</p>
                    <p className="font-medium">{formatPct(bench.expected_volatility)}</p>
                  </div>
                  <div className="space-y-0.5">
                    <p className="text-xs text-muted-foreground">夏普比率</p>
                    <p className="font-medium">{bench.sharpe_ratio?.toFixed(2)}</p>
                  </div>
                  <div className="space-y-0.5">
                    <p className="text-xs text-muted-foreground">分散化比率</p>
                    <p className="font-medium">{bench.diversification_ratio?.toFixed(2)}</p>
                  </div>
                </div>
                <div className="mt-3 p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted-foreground">
                    夏普比率提升: {data.sharpe_ratio && bench.sharpe_ratio
                      ? `${((data.sharpe_ratio - bench.sharpe_ratio) / Math.abs(bench.sharpe_ratio || 0.01) * 100).toFixed(1)}%`
                      : "--"}
                    {" | "}
                    波动率变化: {data.expected_volatility && bench.expected_volatility
                      ? `${((data.expected_volatility - bench.expected_volatility) / bench.expected_volatility * 100).toFixed(1)}%`
                      : "--"}
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* 策略说明 */}
      <InstructionsPanel
        title="组合优化策略说明"
        description="Man Group 风格投资组合构建方法"
        icon="info"
        defaultExpanded={false}
        instructions={[
          {
            title: "最大夏普比率 (Max Sharpe)",
            description: "在有效前沿上寻找收益/风险比最高的组合。适合追求风险调整后收益最大化的投资者。"
          },
          {
            title: "最小方差 (Min Variance)",
            description: "寻找波动率最低的组合。适合保守型投资者，牺牲部分收益换取更低波动。"
          },
          {
            title: "风险平价 (Risk Parity)",
            description: "使每个资产对组合的风险贡献相等。桥水全天候策略的核心思想——不预测收益，只平衡风险。"
          },
          {
            title: "有效前沿 (Efficient Frontier)",
            description: "在给定风险水平下能达到的最高收益的集合。曲线上的每个点都是帕累托最优——无法在不增加风险的情况下提高收益。"
          },
          {
            title: "分散化比率",
            description: "衡量组合分散化程度，值越高表示资金越均匀分布在资产间。计算公式为 1/sqrt(Σw²×N)。"
          },
        ]}
      />
    </div>
  )
}
