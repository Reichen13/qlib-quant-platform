import { useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { Calculator, AlertCircle, CheckCircle2, Target } from "lucide-react"

import { api, type TurtleTradePlanResponse } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

function parseCodes(raw: string | null): string {
  return (raw || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .join("\n")
}

function parseCandidateText(text: string) {
  return text
    .split(/[\n,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 20)
    .map((code) => ({ code, source: "trade_plan_page" }))
}

function formatMoney(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--"
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })
}

export function TradePlanPage() {
  const [searchParams] = useSearchParams()
  const [accountEquity, setAccountEquity] = useState(100000)
  const [riskPercent, setRiskPercent] = useState(1)
  const [candidateText, setCandidateText] = useState(() => parseCodes(searchParams.get("codes")) || "600519\n000001")

  const candidates = useMemo(() => parseCandidateText(candidateText), [candidateText])

  const mutation = useMutation<TurtleTradePlanResponse>({
    mutationFn: () => api.tradePlan.turtle({
      account_equity: accountEquity,
      risk_percent: riskPercent / 100,
      max_units: 4,
      atr_period: 20,
      min_reward_risk: 2,
      candidates,
    }),
  })

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      <div className="space-y-1">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Calculator className="h-7 w-7 text-emerald-600" />
          交易计划
        </h1>
        <p className="text-muted-foreground">
          基于海龟交易法，把候选标的转换为仓位、止损、加仓和盈亏比计划；仅用于风险测算，不自动下单。
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>计划参数</CardTitle>
            <CardDescription>默认使用标准海龟版：单笔风险 1%，最多 4 个单位。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>账户资金</Label>
              <Input
                type="number"
                value={accountEquity}
                min={1000}
                step={1000}
                onChange={(event) => setAccountEquity(Number(event.target.value || 0))}
              />
            </div>
            <div className="space-y-2">
              <Label>单笔风险比例（%）</Label>
              <Input
                type="number"
                value={riskPercent}
                min={0.1}
                max={5}
                step={0.1}
                onChange={(event) => setRiskPercent(Number(event.target.value || 0))}
              />
            </div>
            <div className="space-y-2">
              <Label>候选标的代码</Label>
              <textarea
                className="min-h-32 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={candidateText}
                onChange={(event) => setCandidateText(event.target.value)}
                placeholder="每行一个代码，例如 600519"
              />
              <p className="text-xs text-muted-foreground">最多读取 20 个候选；可从盘后选股页面带入。</p>
            </div>
            <Button className="w-full" onClick={() => mutation.mutate()} disabled={mutation.isPending || candidates.length === 0}>
              {mutation.isPending ? "生成中..." : "生成海龟交易计划"}
            </Button>
          </CardContent>
        </Card>

        <div className="space-y-4">
          {mutation.error ? (
            <Card className="border-destructive/40">
              <CardContent className="flex items-start gap-2 pt-4 text-sm text-destructive">
                <AlertCircle className="mt-0.5 h-4 w-4" />
                <span>{mutation.error instanceof Error ? mutation.error.message : "生成失败"}</span>
              </CardContent>
            </Card>
          ) : null}

          {mutation.data ? (
            <>
              <Card>
                <CardContent className="pt-4 text-sm text-muted-foreground">
                  {mutation.data.disclaimer}
                  {mutation.data.errors.length > 0 ? (
                    <div className="mt-2 text-yellow-600">
                      {mutation.data.errors.length} 个标的因行情或参数不足未生成计划。
                    </div>
                  ) : null}
                </CardContent>
              </Card>

              <div className="grid gap-4 xl:grid-cols-2">
                {mutation.data.plans.map((plan) => (
                  <Card key={plan.code}>
                    <CardHeader>
                      <CardTitle className="flex items-center justify-between gap-2">
                        <span>{plan.name}</span>
                        <Badge variant={plan.verdict === "可执行" ? "default" : "outline"}>{plan.verdict}</Badge>
                      </CardTitle>
                      <CardDescription>{plan.code} · N/ATR {formatMoney(plan.atr)}</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <div className="text-muted-foreground">观察入场</div>
                          <div className="font-medium">{formatMoney(plan.entry_price)}</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground">初始止损</div>
                          <div className="font-medium text-destructive">{formatMoney(plan.initial_stop)}</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground">单单位股数</div>
                          <div className="font-medium">{plan.unit_shares}</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground">单单位金额</div>
                          <div className="font-medium">{formatMoney(plan.unit_position_value)}</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground">最大股数</div>
                          <div className="font-medium">{plan.max_shares}</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground">盈亏比</div>
                          <div className="font-medium">{plan.reward_risk_ratio ?? "待目标价"}</div>
                        </div>
                      </div>

                      <div className="rounded-md bg-muted p-3">
                        <div className="mb-1 flex items-center gap-1 font-medium">
                          <Target className="h-4 w-4" /> 加仓价位
                        </div>
                        <div>{plan.add_on_prices.length ? plan.add_on_prices.map(formatMoney).join(" / ") : "无"}</div>
                      </div>

                      <div className="rounded-md border p-3 text-muted-foreground">{plan.plan_text}</div>

                      {plan.warnings.length > 0 ? (
                        <div className="space-y-1 text-yellow-600">
                          {plan.warnings.map((warning) => (
                            <div key={warning} className="flex items-start gap-1">
                              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                              <span>{warning}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="flex items-center gap-1 text-emerald-600">
                          <CheckCircle2 className="h-4 w-4" /> 风险预算内，盈亏比条件满足。
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </>
          ) : (
            <Card>
              <CardContent className="py-12 text-center text-sm text-muted-foreground">
                填写资金和候选代码后，点击生成交易计划。
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
