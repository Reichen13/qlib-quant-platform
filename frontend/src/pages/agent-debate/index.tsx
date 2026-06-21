// 多智能体辩论页面 - 5阶段分析管道可视化
import { useCallback, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { api } from "@/lib/api"
import { useAppStore } from "@/stores/app-store"
import { MessageSquare, Search, Loader2, TrendingUp, AlertTriangle, Shield, Target, CheckCircle, XCircle } from "lucide-react"

const STAGES = [
  { id: "analysts", label: "分析师团队", icon: Search, color: "bg-blue-500" },
  { id: "debate", label: "研究员辩论", icon: MessageSquare, color: "bg-purple-500" },
  { id: "trade", label: "交易提案", icon: TrendingUp, color: "bg-emerald-500" },
  { id: "risk", label: "风控评估", icon: Shield, color: "bg-amber-500" },
  { id: "pm", label: "PM 决策", icon: Target, color: "bg-red-500" },
]

const RATING_COLORS: Record<string, string> = {
  "强力买入": "bg-emerald-600 text-white",
  "买入": "bg-emerald-100 text-emerald-700",
  "持有": "bg-slate-100 text-slate-600",
  "卖出": "bg-red-100 text-red-700",
  "强力卖出": "bg-red-600 text-white",
}

export function AgentDebatePage() {
  const { agentDebateParams, setAgentDebateParams } = useAppStore()
  const { code, agentDebateTaskId, status, activeStage, memory, errorMessage } = agentDebateParams
  const report = agentDebateParams.report as any

  const pollReport = useCallback(async () => {
    if (!agentDebateTaskId) return
    try {
      const r = await api.agent.report(agentDebateTaskId)
      if (r.status === "completed" || r.status === "failed") {
        setAgentDebateParams({
          status: r.status,
          report: r.report || null,
          errorMessage: r.error || "",
          activeStage: r.report ? 5 : activeStage,
          agentDebateTaskId: null,
        })
      } else {
        setAgentDebateParams({ activeStage: Math.min(activeStage + 1, 4) })
      }
    } catch {
      // Keep polling; transient report lookups can fail while the task is still starting.
    }
  }, [activeStage, agentDebateTaskId, setAgentDebateParams])

  useEffect(() => {
    if (status !== "running" || !agentDebateTaskId) return
    pollReport()
    const interval = setInterval(pollReport, 2000)
    return () => clearInterval(interval)
  }, [agentDebateTaskId, pollReport, status])

  const handleAnalyze = async () => {
    if (!code.trim()) return
    setAgentDebateParams({
      status: "running",
      report: null,
      errorMessage: "",
      activeStage: 0,
      agentDebateTaskId: null,
    })

    try {
      const result = await api.agent.analyze(code.trim(), true)
      setAgentDebateParams({
        agentDebateTaskId: result.task_id,
        status: result.status || "running",
        report: result.report || null,
        errorMessage: result.error || "",
        activeStage: result.report ? 5 : 0,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : "分析请求失败"
      setAgentDebateParams({ status: "error", agentDebateTaskId: null, errorMessage: message })
    }
  }

  // 也获取历史记忆
  const handleLoadMemory = async () => {
    if (!code.trim()) return
    try {
      const result = await api.agent.memory(code.trim())
      setAgentDebateParams({ memory: result.memory || "" })
    } catch { /* ignore */ }
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <MessageSquare className="h-8 w-8 text-slate-600" />
          智能体辩论
        </h1>
        <p className="text-muted-foreground">基于 TradingAgents 架构的 5 阶段多智能体分析管道</p>
      </div>

      {/* 输入 */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-2">
            <Input
              placeholder="输入股票代码，如 600519 / 300750 / 688981"
              value={code}
              onChange={(e) => setAgentDebateParams({ code: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
              className="max-w-sm font-mono"
              disabled={status === "running"}
            />
            <Button onClick={handleAnalyze} disabled={status === "running" || !code.trim()}>
              {status === "running" ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Search className="h-4 w-4 mr-2" />
              )}
              开始分析
            </Button>
            <Button variant="outline" onClick={handleLoadMemory} disabled={!code.trim()}>
              查看历史
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* 阶段进度条 */}
      {status !== "idle" && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-1">
              {STAGES.map((stage, i) => {
                const Icon = stage.icon
                const isActive = i < activeStage
                const isCurrent = i === activeStage && status === "running"
                return (
                  <div key={stage.id} className="flex-1 flex flex-col items-center gap-1">
                    <div className={`flex size-8 items-center justify-center rounded-full text-white text-xs ${isActive ? stage.color : "bg-muted"} ${isCurrent ? "animate-pulse" : ""}`}>
                      {isActive ? <CheckCircle className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
                    </div>
                    <span className="text-[10px] text-muted-foreground text-center">{stage.label}</span>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 错误状态 */}
      {status === "error" && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="pt-6">
            <p className="text-sm text-red-700 flex items-center gap-2">
              <XCircle className="h-4 w-4" />
              分析失败，请检查 LLM 配置或股票代码是否正确
            </p>
            <p className="text-sm text-muted-foreground mt-2">
              {errorMessage || "请检查 LLM 配置、模型名称、Base URL 或股票代码是否正确。"}
            </p>
          </CardContent>
        </Card>
      )}

      {/* 加载状态 */}
      {status === "running" && (
        <Card>
          <CardContent className="pt-6 text-center py-12">
            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-3 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">多智能体分析进行中...</p>
            <p className="text-xs text-muted-foreground mt-1">分析师团队正在协作分析，请耐心等待</p>
          </CardContent>
        </Card>
      )}

      {/* 报告 */}
      {report && (
        <div className="space-y-4">
          {/* Stage 1: 分析师 */}
          {report.stage1_analysts?.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Search className="h-4 w-4 text-blue-500" />
                  Stage 1: 分析师团队
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 md:grid-cols-2">
                  {report.stage1_analysts.map((a: any, i: number) => (
                    <div key={i} className="p-3 bg-muted/30 rounded-lg space-y-2">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium">{a.analyst}</p>
                        <Badge variant="outline" className="text-xs">
                          置信度 {(a.confidence * 100).toFixed(0)}%
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">{a.summary}</p>
                      {a.bullish_factors?.length > 0 && (
                        <div className="text-xs space-y-0.5">
                          <span className="text-emerald-600 font-medium">看多:</span>
                          {a.bullish_factors.map((f: string, j: number) => (
                            <span key={j} className="block text-muted-foreground">• {f}</span>
                          ))}
                        </div>
                      )}
                      {a.bearish_factors?.length > 0 && (
                        <div className="text-xs space-y-0.5">
                          <span className="text-red-600 font-medium">看空:</span>
                          {a.bearish_factors.map((f: string, j: number) => (
                            <span key={j} className="block text-muted-foreground">• {f}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Stage 2: 辩论 */}
          {report.stage2_debate && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-purple-500" />
                  Stage 2: 研究主管裁判
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">方向判断:</span>
                    <Badge className={
                      report.stage2_debate.verdict === "bullish" ? "bg-emerald-100 text-emerald-700" :
                      report.stage2_debate.verdict === "bearish" ? "bg-red-100 text-red-700" :
                      "bg-slate-100 text-slate-600"
                    }>
                      {report.stage2_debate.verdict === "bullish" ? "看多" :
                       report.stage2_debate.verdict === "bearish" ? "看空" : "中性"}
                    </Badge>
                  </div>
                  <p className="text-sm">{report.stage2_debate.thesis}</p>
                  {report.stage2_debate.key_catalysts?.length > 0 && (
                    <div className="text-xs space-y-0.5">
                      <span className="text-emerald-600 font-medium">催化剂:</span>
                      {report.stage2_debate.key_catalysts.map((c: string, i: number) => (
                        <span key={i} className="block text-muted-foreground">• {c}</span>
                      ))}
                    </div>
                  )}
                  {report.stage2_debate.key_risks?.length > 0 && (
                    <div className="text-xs space-y-0.5">
                      <span className="text-red-600 font-medium">风险:</span>
                      {report.stage2_debate.key_risks.map((r: string, i: number) => (
                        <span key={i} className="block text-muted-foreground">• {r}</span>
                      ))}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Stage 3: 交易提案 */}
          {report.stage3_trade && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-emerald-500" />
                  Stage 3: 交易员提案
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-2 md:grid-cols-4">
                  <div className="p-2 bg-muted/30 rounded text-center">
                    <p className="text-xs text-muted-foreground">方向</p>
                    <p className="font-bold text-sm">{report.stage3_trade.direction}</p>
                  </div>
                  <div className="p-2 bg-muted/30 rounded text-center">
                    <p className="text-xs text-muted-foreground">入场价</p>
                    <p className="font-bold text-sm">{report.stage3_trade.entry_price}</p>
                  </div>
                  <div className="p-2 bg-muted/30 rounded text-center">
                    <p className="text-xs text-muted-foreground">止损</p>
                    <p className="font-bold text-sm text-red-600">{report.stage3_trade.stop_loss}</p>
                  </div>
                  <div className="p-2 bg-muted/30 rounded text-center">
                    <p className="text-xs text-muted-foreground">仓位</p>
                    <p className="font-bold text-sm">{(report.stage3_trade.position_pct * 100).toFixed(0)}%</p>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mt-3">{report.stage3_trade.rationale}</p>
              </CardContent>
            </Card>
          )}

          {/* Stage 4: 风控 */}
          {report.stage4_risk && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Shield className="h-4 w-4 text-amber-500" />
                  Stage 4: 风控评估
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">风险等级:</span>
                    <Badge className={
                      report.stage4_risk.risk_level === "low" ? "bg-emerald-100 text-emerald-700" :
                      report.stage4_risk.risk_level === "high" ? "bg-red-100 text-red-700" :
                      "bg-amber-100 text-amber-700"
                    }>
                      {report.stage4_risk.risk_level}
                    </Badge>
                  </div>
                  {report.stage4_risk.key_concerns?.length > 0 && (
                    <div className="text-xs space-y-0.5">
                      <span className="font-medium text-amber-700">关注点:</span>
                      {report.stage4_risk.key_concerns.map((c: string, i: number) => (
                        <span key={i} className="block text-muted-foreground">• {c}</span>
                      ))}
                    </div>
                  )}
                  {report.stage4_risk.mitigation?.length > 0 && (
                    <div className="text-xs space-y-0.5">
                      <span className="font-medium text-emerald-700">缓释措施:</span>
                      {report.stage4_risk.mitigation.map((m: string, i: number) => (
                        <span key={i} className="block text-muted-foreground">• {m}</span>
                      ))}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Stage 5: PM 最终决策 */}
          {report.stage5_decision && (
            <Card className="border-2 border-primary/20">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Target className="h-4 w-4 text-red-500" />
                  Stage 5: 最终决策
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center gap-3">
                  <span className="text-sm">评级:</span>
                  <Badge className={`text-lg px-4 py-1 ${RATING_COLORS[report.stage5_decision.rating] || ""}`}>
                    {report.stage5_decision.rating}
                  </Badge>
                </div>
                <div className="p-3 bg-muted/30 rounded">
                  <p className="text-sm font-medium mb-1">投资逻辑</p>
                  <p className="text-sm text-muted-foreground">{report.stage5_decision.thesis}</p>
                </div>
                <div className="grid gap-2 md:grid-cols-3">
                  <div className="p-2 bg-muted/30 rounded">
                    <p className="text-xs text-muted-foreground">目标价</p>
                    <p className="font-bold">{report.stage5_decision.price_target}</p>
                  </div>
                  <div className="p-2 bg-muted/30 rounded">
                    <p className="text-xs text-muted-foreground">仓位建议</p>
                    <p className="font-bold text-sm">{report.stage5_decision.position_sizing}</p>
                  </div>
                  <div className="p-2 bg-muted/30 rounded">
                    <p className="text-xs text-muted-foreground">投资期限</p>
                    <p className="font-bold text-sm">{report.stage5_decision.time_horizon}</p>
                  </div>
                </div>
                {report.stage5_decision.risk_alerts?.length > 0 && (
                  <div className="p-3 bg-amber-50 rounded space-y-1">
                    <p className="text-xs font-medium text-amber-700 flex items-center gap-1">
                      <AlertTriangle className="h-3 w-3" /> 风险提示
                    </p>
                    {report.stage5_decision.risk_alerts.map((r: string, i: number) => (
                      <p key={i} className="text-xs text-amber-600">• {r}</p>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* 历史记忆 */}
      {memory && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">历史分析记录</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono">{memory || "暂无记录"}</pre>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
