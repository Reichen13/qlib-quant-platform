// 风险管理仪表板 - Two Sigma 风格风险管理系统
import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Shield, Loader2, AlertTriangle, CheckCircle2, X } from "lucide-react"
import { LineChartComponent } from "@/components/charts/line-chart"
import { BarChart } from "@/components/charts/bar-chart"
import { Heatmap } from "@/components/charts/heatmap"
import { InstructionsPanel } from "@/components/features/instructions-panel"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useAppStore } from "@/stores/app-store"

const getRiskBadge = (level: string) => {
  if (level === "低风险") return <Badge variant="default">{level}</Badge>
  if (level === "中等风险") return <Badge className="bg-yellow-600">{level}</Badge>
  if (level === "中高风险") return <Badge className="bg-orange-600">{level}</Badge>
  return <Badge variant="destructive">{level}</Badge>
}

const getImpactColor = (impact: number) => {
  if (impact > -5) return "text-muted-foreground"
  if (impact > -15) return "text-yellow-500"
  return "text-down"
}

const getScenarioBadge = (type: string) => {
  if (type === "historical") return <Badge variant="destructive">历史真实</Badge>
  if (type === "historical_proxy") return <Badge className="bg-orange-600">历史类比</Badge>
  return <Badge variant="outline">假设情景</Badge>
}

export function RiskPage() {
  const riskCodes = useAppStore((s) => s.riskCodes)
  const riskInputValue = useAppStore((s) => s.riskInputValue)
  const setRiskCodes = useAppStore((s) => s.setRiskCodes)
  const [analyzeEnabled, setAnalyzeEnabled] = useState(true)

  // 风险分析
  const { data: riskData, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["risk", "analyze", riskCodes],
    queryFn: () => api.risk.analyze({ codes: riskCodes }),
    enabled: analyzeEnabled && riskCodes.length > 0,
    retry: 1,
  })

  // 每日检查清单
  const { data: checklistData } = useQuery({
    queryKey: ["risk", "checklist"],
    queryFn: () => api.risk.dailyChecklist(),
  })

  const handleAnalyze = () => {
    const parsedCodes = riskInputValue
      .split(/[\s,]+/)
      .map(s => s.trim())
      .filter(Boolean)
    if (parsedCodes.length === 0) return
    setRiskCodes(parsedCodes, riskInputValue)
    setAnalyzeEnabled(true)
    setTimeout(() => refetch(), 0)
  }

  const handleRemoveCode = (code: string) => {
    const newCodes = riskCodes.filter(c => c !== code)
    setRiskCodes(newCodes, newCodes.join(" "))
  }

  const formatPct = (val: number | undefined) => {
    if (val === undefined || val === null) return "--"
    return `${(val * 100).toFixed(2)}%`
  }

  const formatVar = (val: number | undefined) => {
    if (val === undefined || val === null) return "--"
    return `${(val * 100).toFixed(2)}%`
  }

  const metrics = riskData?.metrics
  const stressTests = riskData?.stress_tests || []
  const correlations = riskData?.correlations || []
  const positionSizing = riskData?.position_sizing
  const equity = riskData?.equity || []
  const drawdown = riskData?.drawdown || []
  const errorMessage = (error as any)?.message || "无法获取风险数据，请检查股票代码是否正确"
  const isAuthError = errorMessage.includes("服务器管理 Key") || errorMessage.includes("API Key")

  // 压力测试柱状图数据
  const stressChartData = stressTests.map((s: any) => ({
    name: s.name,
    impact: s.impact,
  }))

  // 相关性热力图数据
  const heatmapRows = [...new Set(correlations.map((c: any) => c.stock1))] as string[]
  const heatmapData = correlations.map((c: any) => ({
    row: c.stock1?.split(".")[0] || c.stock1,
    col: c.stock2?.split(".")[0] || c.stock2,
    value: c.correlation,
    label: c.correlation?.toFixed(2),
  }))

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Shield className="size-5 text-muted-foreground" />
          风险管理
        </h1>
        <p className="text-muted-foreground">Two Sigma 风格风险管理系统 - VaR / 压力测试 / 头寸规模</p>
      </div>

      {/* 股票输入区 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">投资组合配置</CardTitle>
          <CardDescription>
            输入股票代码（空格或逗号分隔），如 600519.SS 000858.SZ
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Input
              value={riskInputValue}
              onChange={(e) => setRiskCodes(riskCodes, e.target.value)}
              placeholder="输入股票代码..."
              className="flex-1 font-mono text-sm"
              onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
            />
            <Button onClick={handleAnalyze} disabled={isLoading}>
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Shield className="h-4 w-4" />}
              <span className="ml-2">开始分析</span>
            </Button>
          </div>
          {riskCodes.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {riskCodes.map(code => (
                <Badge key={code} variant="secondary" className="gap-1">
                  {code}
                  <X
                    className="h-3 w-3 cursor-pointer hover:text-foreground"
                    onClick={() => handleRemoveCode(code)}
                  />
                </Badge>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 加载 / 错误 / 空状态 */}
      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" />
          <span className="ml-3 text-muted-foreground">正在分析风险指标...</span>
        </div>
      )}

      {isError && (
        <Card className="border-down/50 bg-down/5">
          <CardContent className="py-6">
            <div className="flex items-center gap-3 text-down">
              <AlertTriangle className="h-5 w-5" />
              <div>
                <p className="font-medium">风险分析失败</p>
                <p className="text-sm text-muted-foreground mt-1">
                  {isAuthError
                    ? "需要先配置服务器管理 Key。请到数据管理页面填写服务器 API_KEY 后，再回到本页重试。"
                    : errorMessage}
                </p>
                {isAuthError && (
                  <p className="text-xs text-muted-foreground mt-1">
                    原始提示：{errorMessage}
                  </p>
                )}
              </div>
            </div>
            <Button variant="outline" className="mt-4" onClick={() => refetch()}>
              重试
            </Button>
          </CardContent>
        </Card>
      )}

      {riskData && !isLoading && (
        <>
          {/* 风险概览卡片 */}
          <div className="grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">年化收益</CardTitle>
              </CardHeader>
              <CardContent>
                <div className={`text-xl font-bold ${(metrics?.annual_return || 0) >= 0 ? "text-up" : "text-down"}`}>
                  {formatPct(metrics?.annual_return)}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">年化波动</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xl font-bold">
                  {formatPct(metrics?.annual_volatility)}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">Sharpe 比率</CardTitle>
              </CardHeader>
              <CardContent>
                <div className={`text-xl font-bold ${(metrics?.sharpe_ratio || 0) >= 1 ? "text-up" : (metrics?.sharpe_ratio || 0) >= 0 ? "" : "text-down"}`}>
                  {metrics?.sharpe_ratio?.toFixed(2) || "--"}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">最大回撤</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xl font-bold text-down">
                  {formatPct(metrics?.max_drawdown)}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">VaR (95%)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xl font-bold text-down">
                  {formatVar(metrics?.var_95)}
                </div>
                <p className="text-xs text-muted-foreground">
                  CVaR: {formatVar(metrics?.cvar_95)} · 历史模拟法
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">胜率</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xl font-bold">
                  {metrics?.win_rate ? `${(metrics.win_rate * 100).toFixed(1)}%` : "--"}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* 净值曲线 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">组合净值曲线</CardTitle>
              </CardHeader>
              <CardContent>
                {equity.length > 0 ? (
                  <LineChartComponent
                    data={equity}
                    lines={[{ dataKey: "value", name: "组合净值", color: "var(--color-primary)" }]}
                    xKey="date"
                    height={250}
                  />
                ) : (
                  <p className="text-center py-12 text-muted-foreground">暂无净值数据</p>
                )}
              </CardContent>
            </Card>

            {/* 回撤曲线 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">回撤曲线</CardTitle>
                <CardDescription>组合回撤百分比</CardDescription>
              </CardHeader>
              <CardContent>
                {drawdown.length > 0 ? (
                  <LineChartComponent
                    data={drawdown}
                    lines={[{ dataKey: "value", name: "回撤", color: "var(--color-down)" }]}
                    xKey="date"
                    height={250}
                  />
                ) : (
                  <p className="text-center py-12 text-muted-foreground">暂无回撤数据</p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* 压力测试 + 仓位建议 */}
          <div className="grid gap-4 lg:grid-cols-2">
            {/* 压力测试 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-yellow-500" />
                  压力测试
                </CardTitle>
                <CardDescription>历史情景与假设情景分析</CardDescription>
              </CardHeader>
              <CardContent>
                {stressTests.length > 0 ? (
                  <div className="space-y-4">
                    {/* 柱状图 */}
                    <BarChart
                      data={stressChartData}
                      bars={[{ dataKey: "impact", name: "影响 (%)", color: "var(--color-down)" }]}
                      xKey="name"
                      height={180}
                    />

                    {/* 详细表格 */}
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>情景</TableHead>
                          <TableHead>类型</TableHead>
                          <TableHead className="text-right">影响</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {stressTests.map((s: any) => (
                          <TableRow key={s.name}>
                            <TableCell>
                              <div className="space-y-0.5">
                                <div className="font-medium text-sm">{s.name}</div>
                                <div className="text-xs text-muted-foreground">{s.description}</div>
                              </div>
                            </TableCell>
                            <TableCell>{getScenarioBadge(s.scenario_type)}</TableCell>
                            <TableCell className={`text-right font-medium ${getImpactColor(s.impact)}`}>
                              {s.impact.toFixed(1)}%
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                ) : (
                  <p className="text-center py-8 text-muted-foreground">暂无压力测试数据</p>
                )}
              </CardContent>
            </Card>

            {/* 仓位建议 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">头寸规模建议</CardTitle>
                <CardDescription>Kelly 公式与风险评估</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {positionSizing && (
                  <>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground">风险等级：</span>
                      {getRiskBadge(positionSizing.risk_level)}
                    </div>

                    <p className="text-sm p-3 bg-muted rounded-lg">{positionSizing.suggestion}</p>

                    <div className="space-y-2 pt-2">
                      <div className="flex justify-between">
                        <span className="text-sm text-muted-foreground">Kelly 最优仓位</span>
                        <span className="font-medium">{((positionSizing.kelly_fraction || 0) * 100).toFixed(1)}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-muted-foreground">1/2 Kelly（推荐）</span>
                        <span className="font-medium text-up">
                          {((positionSizing.half_kelly || 0) * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-muted-foreground">1/4 Kelly（保守）</span>
                        <span className="font-medium">{((positionSizing.quarter_kelly || 0) * 100).toFixed(1)}%</span>
                      </div>
                    </div>
                  </>
                )}

                {/* 波动率锥 */}
                {metrics?.vol_cone && Object.keys(metrics.vol_cone).length > 0 && (
                  <div className="pt-4 border-t">
                    <p className="text-sm font-medium mb-3">波动率锥</p>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>窗口</TableHead>
                          <TableHead className="text-right">最低</TableHead>
                          <TableHead className="text-right">当前</TableHead>
                          <TableHead className="text-right">最高</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {Object.entries(metrics.vol_cone).map(([window, data]: [string, any]) => (
                          <TableRow key={window}>
                            <TableCell>{window}</TableCell>
                            <TableCell className="text-right">{formatPct(data.min)}</TableCell>
                            <TableCell className="text-right font-medium">{formatPct(data.current)}</TableCell>
                            <TableCell className="text-right">{formatPct(data.max)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* 相关性矩阵 + 每日检查清单 */}
          <div className="grid gap-4 lg:grid-cols-2">
            {/* 相关性矩阵 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">相关性矩阵</CardTitle>
                <CardDescription>
                  股票间相关系数 {metrics?.avg_correlation ? `| 平均: ${metrics.avg_correlation.toFixed(2)}` : ""}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {heatmapData.length > 0 ? (
                  <>
                    <Heatmap
                      data={heatmapData}
                      rowLabels={heatmapRows}
                      colLabels={heatmapRows}
                      title=""
                      description=""
                    />
                    {/* 相关性详情表 */}
                    <div className="mt-4 max-h-40 overflow-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>股票 A</TableHead>
                            <TableHead>股票 B</TableHead>
                            <TableHead className="text-right">相关性</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {correlations.slice(0, 15).map((c: any, i: number) => (
                            <TableRow key={i}>
                              <TableCell className="font-mono text-xs">{c.stock1}</TableCell>
                              <TableCell className="font-mono text-xs">{c.stock2}</TableCell>
                              <TableCell className={`text-right font-medium ${Math.abs(c.correlation) > 0.7 ? "text-yellow-500" : ""}`}>
                                {c.correlation?.toFixed(3)}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </>
                ) : (
                  <p className="text-center py-8 text-muted-foreground">
                    需要至少 2 只股票才能计算相关性
                  </p>
                )}
              </CardContent>
            </Card>

            {/* 每日检查清单 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-up" />
                  每日风险检查清单
                </CardTitle>
                <CardDescription>Two Sigma 风格日风险检查项</CardDescription>
              </CardHeader>
              <CardContent>
                {checklistData?.checklist ? (
                  <div className="space-y-2">
                    {checklistData.checklist.map((item: any) => (
                      <div
                        key={item.id}
                        className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-muted/50 transition-colors"
                      >
                        <div className="mt-0.5">
                          <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
                        </div>
                        <div className="flex-1 space-y-0.5">
                          <p className="text-sm">{item.item}</p>
                          <div className="flex gap-2">
                            <Badge variant="outline" className="text-xs px-1.5 py-0">
                              {item.category}
                            </Badge>
                            <Badge
                              variant={item.priority === "high" ? "destructive" : item.priority === "medium" ? "default" : "outline"}
                              className="text-xs px-1.5 py-0"
                            >
                              {item.priority === "high" ? "高" : item.priority === "medium" ? "中" : "低"}
                            </Badge>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-5 w-5 animate-spin" />
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {/* 策略说明 */}
      <InstructionsPanel
        title="风险管理策略说明"
        description="Two Sigma 风格风险管理系统 - VaR / 压力测试 / 头寸模型"
        icon="info"
        defaultExpanded={false}
        instructions={[
          {
            title: "VaR (Value at Risk)",
            description: "在给定置信水平下，投资组合在特定时间内的最大预期损失。95% VaR 表示有 95% 的概率损失不会超过该值。"
          },
          {
            title: "CVaR (Expected Shortfall)",
            description: "当损失超过 VaR 时的平均损失，衡量尾部风险。比 VaR 更能反映极端情况下的损失。"
          },
          {
            title: "Kelly 公式",
            description: "最优仓位 = (预期收益 - 无风险利率) / 方差。1/2 Kelly 是实践中常用的稳健版本，在收益与风险间取得平衡。"
          },
          {
            title: "压力测试",
            description: "模拟历史极端事件（如 2008 金融危机、2015 A股股灾、2020 新冠）对组合的冲击，评估极端情况下的最大亏损。"
          },
          {
            title: "波动率锥",
            description: "展示不同时间窗口下波动率的分布范围（最低-当前-最高），用于判断当前市场波动处于什么水平。"
          },
        ]}
      />
    </div>
  )
}
