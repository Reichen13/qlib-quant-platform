// 模型回测页面 - LightGBM 策略回测
import { useState, useEffect, useCallback } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Zap, Play, Loader2, TrendingUp, Activity, Settings, BarChart3, ChevronDown, ChevronRight } from "lucide-react"
import { LineChartComponent } from "@/components/charts/line-chart"
import { DrawdownChart } from "@/components/charts/drawdown-chart"
import {
  AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts"
import { OperationAdvice } from "@/components/features/operation-advice"
import { InstructionsPanel, commonInstructions } from "@/components/features/instructions-panel"
import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { BacktestResult } from "@/lib/api"
import { useAppStore } from "@/stores/app-store"

// 默认空结果
const emptyResult: BacktestResult = {
  task_id: "",
  status: "running",
  progress: 0,
  total_return: 0,
  annual_return: 0,
  sharpe_ratio: 0,
  calmar_ratio: 0,
  max_drawdown: 0,
  win_rate: 0,
  profit_loss_ratio: 0,
  equity: [],
  drawdown: [],
  top_buys: [],
  top_sells: [],
  position_advice: "",
}

export function BacktestPage() {
  const activeTab = useAppStore((s) => s.backtestActiveTab)
  const setActiveTab = useAppStore((s) => s.setBacktestActiveTab)
  const params = useAppStore((s) => s.backtestParams)
  const setParams = useAppStore((s) => s.setBacktestParams)
  const [result, setResult] = useState<BacktestResult>(emptyResult)
  const [pollingTaskId, setPollingTaskId] = useState<string | null>(null)
  const [attributionOpen, setAttributionOpen] = useState(true)

  // 运行回测 mutation
  const backtestMutation = useMutation({
    mutationFn: (params: any) => api.backtest.run(params),
    onSuccess: (data) => {
      setPollingTaskId(data.task_id)
      setResult({ ...emptyResult, task_id: data.task_id, status: "running", progress: 5 })
      setActiveTab("results")
    },
    onError: (err) => {
      setResult({ ...emptyResult, status: "failed", error: String(err) })
      setActiveTab("results")
    },
  })

  // 轮询回测状态
  const pollStatus = useCallback(async () => {
    if (!pollingTaskId) return
    try {
      const data = await api.backtest.status(pollingTaskId)
      setResult(data)
      if (data.status === "completed" || data.status === "failed") {
        setPollingTaskId(null)
      }
    } catch {
      setPollingTaskId(null)
    }
  }, [pollingTaskId])

  useEffect(() => {
    if (!pollingTaskId) return
    // 立即查询一次
    pollStatus()
    // 每3秒轮询
    const interval = setInterval(pollStatus, 3000)
    return () => clearInterval(interval)
  }, [pollingTaskId, pollStatus])

  const runBacktest = () => {
    const snakeParams: Record<string, any> = {
      model: params.model,
      train_start: params.trainStart,
      train_end: params.trainEnd,
      test_start: params.testStart,
      test_end: params.testEnd,
      hold_num: parseInt(params.topK),
      turnover: parseInt(params.rebalance),
      buy_cost: parseFloat(params.commission),
      sell_cost: parseFloat(params.slippage),
      max_position: parseFloat(params.singlePosition),
      stop_loss: parseFloat(params.stopLoss),
    }
    if (params.sourceFactor) {
      snakeParams.source_factor = params.sourceFactor
      snakeParams.selected_factors = [params.sourceFactor]
    }
    backtestMutation.mutate(snakeParams)
  }

  const isRunning = result.status === "running"
  const isCompleted = result.status === "completed"
  const isFailed = result.status === "failed"

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Zap className="h-8 w-8 text-yellow-600" />
          模型回测
        </h1>
        <p className="text-muted-foreground">LightGBM / XGBoost 策略回测与收益分析（Alpha158 + Qlib）</p>
      </div>

      {/* 标签页 */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full max-w-md grid-cols-3">
          <TabsTrigger value="config">
            <Settings className="mr-2 h-4 w-4" />
            参数配置
          </TabsTrigger>
          <TabsTrigger value="results">
            <BarChart3 className="mr-2 h-4 w-4" />
            回测结果
          </TabsTrigger>
          <TabsTrigger value="advice">
            <TrendingUp className="mr-2 h-4 w-4" />
            操作建议
          </TabsTrigger>
        </TabsList>

        {/* 参数配置 */}
        <TabsContent value="config" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-3">
            {/* 基础参数 */}
            <Card>
              <CardHeader>
                <CardTitle>基础参数</CardTitle>
                <CardDescription>设置模型和训练参数</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>模型类型</Label>
                  <Select
                    value={params.model}
                    onValueChange={(v) => setParams({ ...params, model: v })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="lightgbm">LightGBM</SelectItem>
                      <SelectItem value="xgboost">XGBoost</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>训练起始日</Label>
                    <Input
                      type="date"
                      value={params.trainStart}
                      onChange={(e) => setParams({ ...params, trainStart: e.target.value })}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label>训练结束日</Label>
                    <Input
                      type="date"
                      value={params.trainEnd}
                      onChange={(e) => setParams({ ...params, trainEnd: e.target.value })}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>测试起始日</Label>
                    <Input
                      type="date"
                      value={params.testStart}
                      onChange={(e) => setParams({ ...params, testStart: e.target.value })}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label>测试结束日</Label>
                    <Input
                      type="date"
                      value={params.testEnd}
                      onChange={(e) => setParams({ ...params, testEnd: e.target.value })}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* 策略参数 */}
            <Card>
              <CardHeader>
                <CardTitle>策略参数</CardTitle>
                <CardDescription>设置交易策略参数</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>选股数量 (Top K)</Label>
                  <Input
                    type="number"
                    value={params.topK}
                    onChange={(e) => setParams({ ...params, topK: e.target.value })}
                  />
                  <p className="text-xs text-muted-foreground">每期选择评分最高的 K 只股票</p>
                </div>

                <div className="space-y-2">
                  <Label>调仓周期 (天)</Label>
                  <Input
                    type="number"
                    value={params.rebalance}
                    onChange={(e) => setParams({ ...params, rebalance: e.target.value })}
                  />
                  <p className="text-xs text-muted-foreground">每隔 N 天调仓一次</p>
                </div>

                <div className="space-y-2">
                  <Label>单票仓位上限</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={params.singlePosition}
                    onChange={(e) => setParams({ ...params, singlePosition: e.target.value })}
                  />
                  <p className="text-xs text-muted-foreground">单只股票最大持仓比例</p>
                </div>
              </CardContent>
            </Card>

            {/* 风控参数 */}
            <Card>
              <CardHeader>
                <CardTitle>风控参数</CardTitle>
                <CardDescription>设置交易成本和止损</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>买入佣金</Label>
                  <Input
                    type="number"
                    step="0.0001"
                    value={params.commission}
                    onChange={(e) => setParams({ ...params, commission: e.target.value })}
                  />
                  <p className="text-xs text-muted-foreground">买入佣金率（默认万三）</p>
                </div>

                <div className="space-y-2">
                  <Label>卖出佣金</Label>
                  <Input
                    type="number"
                    step="0.0001"
                    value={params.slippage}
                    onChange={(e) => setParams({ ...params, slippage: e.target.value })}
                  />
                  <p className="text-xs text-muted-foreground">卖出佣金率（默认万三）</p>
                </div>

                <div className="space-y-2">
                  <Label>止损位</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={params.stopLoss}
                    onChange={(e) => setParams({ ...params, stopLoss: e.target.value })}
                  />
                  <p className="text-xs text-muted-foreground">单只股票亏损达到此比例止损</p>
                </div>

                <Button
                  className="w-full"
                  onClick={runBacktest}
                  disabled={backtestMutation.isPending || !!pollingTaskId}
                >
                  {backtestMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      提交中...
                    </>
                  ) : pollingTaskId ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      回测中...
                    </>
                  ) : (
                    <>
                      <Play className="mr-2 h-4 w-4" />
                      运行回测
                    </>
                  )}
                </Button>

                {backtestMutation.data && !pollingTaskId && (
                  <div className="p-3 bg-green-500/10 rounded-lg">
                    <p className="text-sm text-green-600">回测已完成</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      任务ID: {backtestMutation.data.task_id?.slice(0, 8)}...
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* 回测结果 */}
        <TabsContent value="results" className="space-y-6">
          {isRunning ? (
            <div className="flex flex-col items-center justify-center py-16 space-y-4">
              <Loader2 className="h-12 w-12 animate-spin text-yellow-600" />
              <div className="text-center">
                <p className="text-lg font-medium">回测运行中...</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Alpha158 特征工程 + 模型训练 + 策略回测，预计 2-5 分钟
                </p>
                {result.progress != null && (
                  <div className="mt-4 w-64">
                    <div className="bg-muted rounded-full h-2">
                      <div
                        className="bg-yellow-600 rounded-full h-2 transition-all duration-500"
                        style={{ width: `${result.progress}%` }}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">{result.progress}%</p>
                  </div>
                )}
              </div>
            </div>
          ) : isFailed ? (
            <Card>
              <CardContent className="py-8 text-center">
                <p className="text-lg font-medium text-red-500">回测失败</p>
                <p className="text-sm text-muted-foreground mt-2">{result.error || "未知错误"}</p>
                <Button variant="outline" className="mt-4" onClick={() => setActiveTab("config")}>
                  返回修改参数
                </Button>
              </CardContent>
            </Card>
          ) : isCompleted && result.equity && result.equity.length > 0 ? (
            <>
              {/* 因子来源横幅 */}
              {result.factor_source && (
                <Card className="border-purple-600/30 bg-purple-600/5">
                  <CardContent className="py-3">
                    <div className="flex items-center gap-2 text-sm">
                      <Badge variant="default" className="bg-purple-600">因子分析跳转</Badge>
                      <span className="text-muted-foreground">
                        当前回测基于因子 <span className="font-medium text-foreground">{result.factor_source}</span> 的选股信号
                      </span>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* 绩效指标 */}
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      总收益率
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className={`text-2xl font-bold ${result.total_return! >= 0 ? "text-up" : "text-down"}`}>
                      {((result.total_return ?? 0) * 100).toFixed(2)}%
                    </div>
                    <p className="text-xs text-muted-foreground">
                      年化: {((result.annual_return ?? 0) * 100).toFixed(2)}%
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      夏普比率
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">
                      {(result.sharpe_ratio ?? 0).toFixed(2)}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {(result.sharpe_ratio ?? 0) > 1 ? "优秀" : (result.sharpe_ratio ?? 0) > 0.5 ? "良好" : "一般"}
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Calmar 比率
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">
                      {(result.calmar_ratio ?? 0).toFixed(2)}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      收益回撤比
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      最大回撤
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-down">
                      {((result.max_drawdown ?? 0) * 100).toFixed(2)}%
                    </div>
                    <p className="text-xs text-muted-foreground">
                      风险控制水平
                    </p>
                  </CardContent>
                </Card>
              </div>

              {/* 收益曲线 */}
              <LineChartComponent
                data={result.equity ?? []}
                lines={[
                  { dataKey: "value", name: "策略净值", color: "var(--color-up)" },
                  { dataKey: "benchmark", name: "基准收益", color: "var(--color-muted-foreground)" },
                ]}
                xKey="date"
                height={300}
              />

              {/* 回撤分析 */}
              <div className="grid gap-6 lg:grid-cols-2">
                <DrawdownChart
                  data={result.drawdown ?? []}
                  height={300}
                  title="回撤曲线"
                  description="策略历史回撤情况"
                />

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Activity className="h-5 w-5" />
                      详细回撤分析
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">最大回撤</span>
                          <span className="text-sm font-medium text-down">
                            {((result.max_drawdown ?? 0) * 100).toFixed(2)}%
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">胜率</span>
                          <span className="text-sm font-medium">
                            {((result.win_rate ?? 0) * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">盈亏比</span>
                          <span className="text-sm font-medium">
                            {(result.profit_loss_ratio ?? 0).toFixed(2)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">Sortino 比率</span>
                          <span className="text-sm font-medium">
                            {(result.sortino_ratio ?? 0).toFixed(2)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">信息比率</span>
                          <span className="text-sm font-medium">
                            {(result.information_ratio ?? 0).toFixed(2)}
                          </span>
                        </div>
                      </div>

                      <div className="pt-4 border-t space-y-3">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">统计检验</p>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">t 统计量</span>
                          <span className={`text-sm font-medium ${(result.t_statistic ?? 0) > 1.96 ? "text-up" : ""}`}>
                            {(result.t_statistic ?? 0).toFixed(3)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">p-value</span>
                          <span className={`text-sm font-medium ${(result.p_value ?? 1) < 0.05 ? "text-up" : "text-down"}`}>
                            {(result.p_value ?? 0).toFixed(4)}
                            {(result.p_value ?? 0) < 0.05 ? " ★" : ""}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">月度胜率</span>
                          <span className="text-sm font-medium">
                            {((result.monthly_win_rate ?? 0) * 100).toFixed(1)}%
                          </span>
                        </div>
                      </div>

                      <div className="pt-4 border-t space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">总收益率</span>
                          <span className={`text-sm font-medium ${result.total_return! >= 0 ? "text-up" : "text-down"}`}>
                            {((result.total_return ?? 0) * 100).toFixed(2)}%
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">年化收益率</span>
                          <span className={`text-sm font-medium ${result.annual_return! >= 0 ? "text-up" : "text-down"}`}>
                            {((result.annual_return ?? 0) * 100).toFixed(2)}%
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">Calmar 比率</span>
                          <span className="text-sm font-medium">
                            {(result.calmar_ratio ?? 0).toFixed(2)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* 绩效归因 (Brinson) */}
              {result.attribution && result.attribution_curve && result.attribution_curve.length > 0 && (
                <Card>
                  <CardHeader
                    className="cursor-pointer select-none"
                    onClick={() => setAttributionOpen(!attributionOpen)}
                  >
                    <CardTitle className="flex items-center gap-2 text-base">
                      {attributionOpen ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                      绩效归因 (Brinson)
                    </CardTitle>
                    <CardDescription>
                      相对 CSI300 基准的超额收益分解
                      <span className="text-xs text-muted-foreground ml-1">(等权基准近似)</span>
                    </CardDescription>
                  </CardHeader>

                  {attributionOpen && (
                    <CardContent className="space-y-6">
                      {/* Summary KPIs */}
                      <div className="grid grid-cols-3 gap-4">
                        <div className="p-4 bg-muted/50 rounded-lg text-center">
                          <p className="text-xs text-muted-foreground mb-1">配置效应</p>
                          <p className={`text-xl font-bold ${result.attribution.allocation_effect >= 0 ? "text-up" : "text-down"}`}>
                            {result.attribution.allocation_effect > 0 ? "+" : ""}
                            {result.attribution.allocation_effect.toFixed(2)}%
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">行业超/低配</p>
                        </div>
                        <div className="p-4 bg-muted/50 rounded-lg text-center">
                          <p className="text-xs text-muted-foreground mb-1">选股效应</p>
                          <p className={`text-xl font-bold ${result.attribution.selection_effect >= 0 ? "text-up" : "text-down"}`}>
                            {result.attribution.selection_effect > 0 ? "+" : ""}
                            {result.attribution.selection_effect.toFixed(2)}%
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">行业内选股</p>
                        </div>
                        <div className="p-4 bg-muted/50 rounded-lg text-center">
                          <p className="text-xs text-muted-foreground mb-1">交互效应</p>
                          <p className={`text-xl font-bold ${result.attribution.interaction_effect >= 0 ? "text-up" : "text-down"}`}>
                            {result.attribution.interaction_effect > 0 ? "+" : ""}
                            {result.attribution.interaction_effect.toFixed(2)}%
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">配置x选股</p>
                        </div>
                      </div>

                      {/* Cumulative Attribution Stacked Area Chart */}
                      <div>
                        <p className="text-sm font-medium mb-3">累计归因分解</p>
                        <ResponsiveContainer width="100%" height={250}>
                          <AreaChart data={result.attribution_curve}>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                            <XAxis dataKey="date" stroke="var(--muted-foreground)" fontSize={12} />
                            <YAxis
                              stroke="var(--muted-foreground)"
                              fontSize={12}
                              tickFormatter={(v: any) => `${(v as number).toFixed(1)}%`}
                            />
                            <Tooltip
                              contentStyle={{
                                backgroundColor: "var(--popover)",
                                border: "1px solid var(--border)",
                                borderRadius: "6px",
                              }}
                              formatter={(v: any) => `${(v as number).toFixed(2)}%`}
                            />
                            <Legend />
                            <Area
                              type="monotone"
                              dataKey="allocation"
                              name="配置效应"
                              stackId="1"
                              stroke="#22c55e"
                              fill="#22c55e"
                              fillOpacity={0.3}
                            />
                            <Area
                              type="monotone"
                              dataKey="selection"
                              name="选股效应"
                              stackId="1"
                              stroke="#3b82f6"
                              fill="#3b82f6"
                              fillOpacity={0.3}
                            />
                            <Area
                              type="monotone"
                              dataKey="interaction"
                              name="交互效应"
                              stackId="1"
                              stroke="#94a3b8"
                              fill="#94a3b8"
                              fillOpacity={0.3}
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>

                      {/* Interpretation */}
                      {result.attribution_interpretation && (
                        <div className="p-4 bg-muted/50 rounded-lg">
                          <p className="text-sm font-medium mb-1">归因解读</p>
                          <p className="text-sm text-muted-foreground">
                            {result.attribution_interpretation}
                          </p>
                        </div>
                      )}

                      {/* Industry Breakdown */}
                      {result.attribution.by_industry && Object.keys(result.attribution.by_industry).length > 0 && (
                        <div>
                          <p className="text-sm font-medium mb-3">行业贡献明细</p>
                          <div className="border rounded-lg overflow-hidden">
                            <table className="w-full text-sm">
                              <thead className="bg-muted/50">
                                <tr>
                                  <th className="text-left px-4 py-2 font-medium">行业</th>
                                  <th className="text-right px-4 py-2 font-medium">配置贡献(%)</th>
                                  <th className="text-right px-4 py-2 font-medium">选股贡献(%)</th>
                                  <th className="text-right px-4 py-2 font-medium">总贡献(%)</th>
                                </tr>
                              </thead>
                              <tbody>
                                {Object.entries(result.attribution.by_industry)
                                  .map(([ind, v]) => ({
                                    industry: ind,
                                    allocation: v.allocation,
                                    selection: v.selection,
                                    total: v.allocation + v.selection,
                                  }))
                                  .sort((a, b) => Math.abs(b.total) - Math.abs(a.total))
                                  .slice(0, 10)
                                  .map((row) => (
                                    <tr key={row.industry} className="border-t">
                                      <td className="px-4 py-2">{row.industry}</td>
                                      <td className={`text-right px-4 py-2 ${row.allocation >= 0 ? "text-up" : "text-down"}`}>
                                        {row.allocation > 0 ? "+" : ""}{row.allocation.toFixed(2)}
                                      </td>
                                      <td className={`text-right px-4 py-2 ${row.selection >= 0 ? "text-up" : "text-down"}`}>
                                        {row.selection > 0 ? "+" : ""}{row.selection.toFixed(2)}
                                      </td>
                                      <td className={`text-right px-4 py-2 font-medium ${row.total >= 0 ? "text-up" : "text-down"}`}>
                                        {row.total > 0 ? "+" : ""}{row.total.toFixed(2)}
                                      </td>
                                    </tr>
                                  ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </CardContent>
                  )}
                </Card>
              )}
            </>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <BarChart3 className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <p className="text-lg font-medium">暂无回测结果</p>
                <p className="text-sm text-muted-foreground mt-1">请先在"参数配置"中运行一次回测</p>
                <Button variant="outline" className="mt-4" onClick={() => setActiveTab("config")}>
                  前往配置
                </Button>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* 操作建议 */}
        <TabsContent value="advice">
          {isCompleted && result.top_buys && result.top_buys.length > 0 ? (
            <>
              <OperationAdvice
                topBuys={result.top_buys}
                topSells={result.top_sells ?? []}
                positionAdvice={result.position_advice ?? ""}
                riskLevel="medium"
                lastUpdate={new Date().toLocaleDateString()}
              />
              {/* A 股约束分析 */}
              {result.constraint_analysis?.constraints_active && (
                <Card className="mt-4 border-blue-600/30 bg-blue-600/5">
                  <CardHeader>
                    <CardTitle className="text-base">A 股交易约束</CardTitle>
                    <CardDescription>回测已启用的 A 股特有约束</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2 text-sm">
                      {result.constraint_analysis.constraints_active.map((c: string, i: number) => (
                        <div key={i} className="flex items-center gap-2">
                          <Badge variant="outline" className="shrink-0">✓</Badge>
                          <span className="text-muted-foreground">{c}</span>
                        </div>
                      ))}
                    </div>
                    {result.constraint_analysis.original_universe != null && (
                      <div className="mt-4 grid gap-2 md:grid-cols-3 text-sm">
                        <div className="p-3 bg-muted/50 rounded">
                          <p className="text-muted-foreground text-xs">原始成分股</p>
                          <p className="font-bold">{result.constraint_analysis.original_universe}</p>
                        </div>
                        <div className="p-3 bg-muted/50 rounded">
                          <p className="text-muted-foreground text-xs">有效成分股</p>
                          <p className="font-bold">{result.constraint_analysis.valid_universe}</p>
                        </div>
                        <div className="p-3 bg-muted/50 rounded">
                          <p className="text-muted-foreground text-xs">已排除(科创/创业)</p>
                          <p className="font-bold text-down">{result.constraint_analysis.excluded_chi_next_star}</p>
                        </div>
                      </div>
                    )}
                    {(result.constraint_analysis.limit_up_hits_estimated != null || result.constraint_analysis.suspended_stocks_estimated != null) && (
                      <div className="mt-3 grid gap-2 md:grid-cols-3 text-sm">
                        <div className="p-3 bg-muted/50 rounded">
                          <p className="text-muted-foreground text-xs">涨停触及次数(估)</p>
                          <p className="font-bold text-up">{result.constraint_analysis.limit_up_hits_estimated ?? "--"}</p>
                        </div>
                        <div className="p-3 bg-muted/50 rounded">
                          <p className="text-muted-foreground text-xs">跌停触及次数(估)</p>
                          <p className="font-bold text-down">{result.constraint_analysis.limit_down_hits_estimated ?? "--"}</p>
                        </div>
                        <div className="p-3 bg-muted/50 rounded">
                          <p className="text-muted-foreground text-xs">停牌股票(估)</p>
                          <p className="font-bold">{result.constraint_analysis.suspended_stocks_estimated ?? "--"}</p>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
              <InstructionsPanel
                title="回测策略说明"
                description="LightGBM 机器学习模型回测参数说明"
                icon="info"
                defaultExpanded={false}
                variant="compact"
                instructions={commonInstructions.backtest}
              />
            </>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <TrendingUp className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <p className="text-lg font-medium">暂无操作建议</p>
                <p className="text-sm text-muted-foreground mt-1">请先运行回测，完成后将自动生成操作建议</p>
                <Button variant="outline" className="mt-4" onClick={() => setActiveTab("config")}>
                  前往配置
                </Button>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
