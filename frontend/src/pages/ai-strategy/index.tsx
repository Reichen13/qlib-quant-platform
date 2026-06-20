// AI 策略页面 - NL策略生成 + 持仓分析 + 参数优化
import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useAppStore } from "@/stores/app-store"
import { Bot, Wand2, Lightbulb, AlertTriangle, ChevronRight, Loader2, Sparkles, Code2, BarChart3, CheckCircle } from "lucide-react"

const CATEGORY_LABELS: Record<string, string> = {
  trend: "趋势跟踪",
  momentum: "动量",
  value: "价值投资",
  mean_reversion: "均值回归",
  factor_rotation: "因子轮动",
}

export function AiStrategyPage() {
  const { aiStrategyParams, setAiStrategyParams } = useAppStore()
  const {
    activeTab,
    nlInput,
    useDeep,
    holdingsInput,
    optimizeStrategy,
  } = aiStrategyParams
  const generated = aiStrategyParams.generated as any
  const analysis = aiStrategyParams.analysis as any
  const optimizeResult = aiStrategyParams.optimizeResult as any
  const [generating, setGenerating] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [optimizing, setOptimizing] = useState(false)

  // 获取模板
  const { data: templates } = useQuery({
    queryKey: ["ai-strategy", "templates"],
    queryFn: () => api.aiStrategy.templates(),
    staleTime: 10 * 60 * 1000,
  })

  const handleGenerate = async () => {
    if (!nlInput.trim()) return
    setGenerating(true)
    setAiStrategyParams({ generated: null })
    try {
      const result = await api.aiStrategy.generate(nlInput, useDeep)
      setAiStrategyParams({ generated: result })
    } catch {
      setAiStrategyParams({ generated: { error: "生成失败，请检查 LLM 配置" } })
    } finally {
      setGenerating(false)
    }
  }

  const handleAnalyze = async () => {
    if (!holdingsInput.trim()) return
    setAnalyzing(true)
    setAiStrategyParams({ analysis: null })
    try {
      // 解析持仓输入: "600519.SS 贵州茅台 0.3, 000858.SZ 五粮液 0.2"
      const holdings = holdingsInput.split(",").map(s => {
        const parts = s.trim().split(/\s+/)
        return {
          code: parts[0] || "",
          name: parts[1] || "",
          weight: parseFloat(parts[2]) || 0,
        }
      }).filter(h => h.code && h.weight > 0)

      const result = await api.aiStrategy.analyze(holdings)
      setAiStrategyParams({ analysis: result })
    } catch {
      setAiStrategyParams({ analysis: { error: "分析失败，请检查 LLM 配置" } })
    } finally {
      setAnalyzing(false)
    }
  }

  const handleOptimize = async () => {
    if (!optimizeStrategy.trim()) return
    setOptimizing(true)
    setAiStrategyParams({ optimizeResult: null })
    try {
      const result = await api.aiStrategy.optimize(optimizeStrategy)
      setAiStrategyParams({ optimizeResult: result })
    } catch {
      setAiStrategyParams({ optimizeResult: { error: "优化失败，请检查 LLM 配置" } })
    } finally {
      setOptimizing(false)
    }
  }

  const actionLabel = (action: string) => {
    switch (action) {
      case "add": return { label: "增持", cls: "bg-emerald-100 text-emerald-700" }
      case "reduce": return { label: "减持", cls: "bg-amber-100 text-amber-700" }
      case "close": return { label: "清仓", cls: "bg-red-100 text-red-700" }
      case "hold": return { label: "持有", cls: "bg-slate-100 text-slate-600" }
      default: return { label: action, cls: "" }
    }
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Bot className="h-8 w-8 text-slate-600" />
          AI 策略
        </h1>
        <p className="text-muted-foreground">LLM 驱动的策略生成、分析与优化</p>
      </div>

      <Tabs value={activeTab} onValueChange={(value) => setAiStrategyParams({ activeTab: value as any })} className="space-y-4">
        <TabsList>
          <TabsTrigger value="generate">
            <Wand2 className="h-4 w-4 mr-1" />
            NL 策略生成
          </TabsTrigger>
          <TabsTrigger value="analyze">
            <BarChart3 className="h-4 w-4 mr-1" />
            持仓分析
          </TabsTrigger>
          <TabsTrigger value="optimize">
            <Sparkles className="h-4 w-4 mr-1" />
            参数优化
          </TabsTrigger>
          <TabsTrigger value="templates">
            <Lightbulb className="h-4 w-4 mr-1" />
            策略模板
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: NL 策略生成 */}
        <TabsContent value="generate" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">自然语言 → 回测策略</CardTitle>
              <CardDescription>用自然语言描述你的交易想法，AI 将其转换为可回测的策略参数</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <textarea
                placeholder='例如："买入沪深300中ROE>15%且处于60日均线以上的股票，每月调仓，单票不超过10%，止损-8%"'
                value={nlInput}
                onChange={(e) => setAiStrategyParams({ nlInput: e.target.value })}
                className="min-h-24 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
              <div className="flex items-center gap-3">
                <Button onClick={handleGenerate} disabled={generating || !nlInput.trim()}>
                  {generating ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <Wand2 className="h-4 w-4 mr-2" />
                  )}
                  生成策略
                </Button>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={useDeep}
                    onChange={(e) => setAiStrategyParams({ useDeep: e.target.checked })}
                    className="rounded"
                  />
                  深度推理
                </label>
              </div>

              {generated?.params && (
                <div className="space-y-3 p-4 bg-muted/30 rounded-lg">
                  <h4 className="text-sm font-semibold flex items-center gap-1">
                    <CheckCircle className="h-4 w-4 text-emerald-600" />
                    生成结果
                  </h4>
                  {generated.params.interpretation && (
                    <div className="p-3 bg-blue-50 rounded text-sm text-blue-800">
                      <Lightbulb className="h-4 w-4 inline mr-1" />
                      {generated.params.interpretation}
                    </div>
                  )}
                  {generated.params.signal_logic && (
                    <div className="p-3 bg-slate-800 rounded text-sm text-slate-100">
                      <Code2 className="h-4 w-4 inline mr-1" />
                      <pre className="text-xs mt-1 whitespace-pre-wrap font-mono">{generated.params.signal_logic}</pre>
                    </div>
                  )}
                  {generated.params.warnings && (
                    <div className="p-3 bg-amber-50 rounded text-sm text-amber-800">
                      <AlertTriangle className="h-4 w-4 inline mr-1" />
                      风险提示: {Array.isArray(generated.params.warnings)
                        ? generated.params.warnings.join("；")
                        : generated.params.warnings}
                    </div>
                  )}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                    {Object.entries(generated.params).filter(([k]) =>
                      ["model", "hold_num", "turnover", "max_position", "stop_loss", "buy_cost", "sell_cost",
                       "train_start", "train_end", "test_start", "test_end"].includes(k)
                    ).map(([k, v]) => (
                      <div key={k} className="p-2 bg-muted rounded">
                        <p className="text-xs text-muted-foreground">{k}</p>
                        <p className="font-mono font-medium">{String(v)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {generated?.raw_output && (
                <div className="p-3 bg-muted/30 rounded text-sm">
                  <p className="text-muted-foreground mb-2">无法解析结构化参数，原始输出:</p>
                  <pre className="text-xs whitespace-pre-wrap font-mono">{generated.raw_output}</pre>
                </div>
              )}

              {generated?.error && (
                <div className="p-3 bg-red-50 rounded text-sm text-red-700">{generated.error}</div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: 持仓分析 */}
        <TabsContent value="analyze" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">AI 持仓分析</CardTitle>
              <CardDescription>输入当前持仓，AI 评估结构并提供调仓建议</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">持仓输入格式: 代码 名称 权重, ...</label>
                <textarea
                  placeholder="600519.SS 贵州茅台 0.25, 000858.SZ 五粮液 0.15, 300750.SZ 宁德时代 0.2, 601318.SS 中国平安 0.1"
                  value={holdingsInput}
                  onChange={(e) => setAiStrategyParams({ holdingsInput: e.target.value })}
                  className="min-h-20 w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
              <Button onClick={handleAnalyze} disabled={analyzing || !holdingsInput.trim()}>
                {analyzing ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <BarChart3 className="h-4 w-4 mr-2" />}
                分析持仓
              </Button>

              {analysis?.analysis && !analysis.analysis.raw && (
                <div className="space-y-4">
                  <div className="p-4 bg-muted/30 rounded-lg">
                    <p className="text-sm font-medium mb-1">总体评估</p>
                    <p className="text-sm text-muted-foreground">{analysis.analysis.overall_assessment}</p>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 bg-muted/30 rounded-lg text-center">
                      <p className="text-xs text-muted-foreground">结构得分</p>
                      <p className="text-xl font-bold">{analysis.analysis.structure_score}/100</p>
                    </div>
                    <div className="p-3 bg-muted/30 rounded-lg text-center">
                      <p className="text-xs text-muted-foreground">风险得分</p>
                      <p className="text-xl font-bold">{analysis.analysis.risk_score}/100</p>
                    </div>
                  </div>

                  {analysis.analysis.suggestions?.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-sm font-medium">调仓建议</p>
                      {analysis.analysis.suggestions.map((s: any, i: number) => {
                        const act = actionLabel(s.action)
                        return (
                          <div key={i} className="flex items-center gap-3 p-3 bg-muted/30 rounded-lg">
                            <Badge className={act.cls}>{act.label}</Badge>
                            <span className="font-mono text-sm">{s.code}</span>
                            {s.target_weight != null && (
                              <span className="text-sm text-muted-foreground">
                                目标 {(s.target_weight * 100).toFixed(0)}%
                              </span>
                            )}
                            <span className="text-sm flex-1 text-right">{s.reason}</span>
                          </div>
                        )
                      })}
                    </div>
                  )}

                  {analysis.analysis.risk_alerts?.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-amber-700 flex items-center gap-1">
                        <AlertTriangle className="h-4 w-4" /> 风险提示
                      </p>
                      {analysis.analysis.risk_alerts.map((r: string, i: number) => (
                        <p key={i} className="text-xs text-muted-foreground">• {r}</p>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {analysis?.analysis?.raw && (
                <div className="p-3 bg-muted/30 rounded text-sm">
                  <pre className="text-xs whitespace-pre-wrap">{analysis.analysis.overall_assessment}</pre>
                </div>
              )}

              {analysis?.error && (
                <div className="p-3 bg-red-50 rounded text-sm text-red-700">{analysis.error}</div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 3: 参数优化 */}
        <TabsContent value="optimize" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">AI 参数优化</CardTitle>
              <CardDescription>AI 基于经验和市场知识建议参数候选组合</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Input
                  placeholder="策略类型，如 momentum_breakout 或 均线交叉"
                  value={optimizeStrategy}
                  onChange={(e) => setAiStrategyParams({ optimizeStrategy: e.target.value })}
                  className="max-w-md"
                />
                <Button onClick={handleOptimize} disabled={optimizing || !optimizeStrategy.trim()}>
                  {optimizing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  <span className="ml-2">建议参数</span>
                </Button>
              </div>

              {optimizeResult?.candidates?.length > 0 && (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground">{optimizeResult.suggestion}</p>
                  {optimizeResult.candidates.map((c: any, i: number) => (
                    <div key={i} className="p-4 bg-muted/30 rounded-lg space-y-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs">{c.name}</Badge>
                        <span className="text-xs text-muted-foreground">{c.expected_characteristics}</span>
                      </div>
                      <p className="text-xs text-muted-foreground">{c.rationale}</p>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-1">
                        {Object.entries(c.params || {}).map(([k, v]) => (
                          <div key={k} className="text-xs p-1 bg-muted rounded">
                            <span className="text-muted-foreground">{k}: </span>
                            <span className="font-mono">{JSON.stringify(v)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {optimizeResult?.error && (
                <div className="p-3 bg-red-50 rounded text-sm text-red-700">{optimizeResult.error}</div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 4: 策略模板 */}
        <TabsContent value="templates" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            {(templates?.templates || []).map((t: any) => (
              <Card key={t.id} className="hover:shadow-md transition-shadow">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{t.name}</CardTitle>
                    <Badge variant="outline" className="text-xs">
                      {CATEGORY_LABELS[t.category] || t.category}
                    </Badge>
                  </div>
                  <CardDescription>{t.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground mb-2">默认参数:</p>
                    <div className="grid grid-cols-2 gap-1">
                      {Object.entries(t.default_params || {}).map(([k, v]) => (
                        <div key={k} className="text-xs p-1 bg-muted/50 rounded flex justify-between">
                          <span className="text-muted-foreground">{k}</span>
                          <span className="font-mono">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-3 w-full"
                    onClick={() => {
                      setAiStrategyParams({ nlInput: t.description, activeTab: "generate" })
                    }}
                  >
                    使用此模板 <ChevronRight className="h-3 w-3 ml-1" />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
