import { useMemo } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { AlertCircle, CheckCircle2, Clock3, Eye, ListChecks, Loader2, RefreshCw, ShieldAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api, type ScreeningCandidate, type ScreeningRunResponse } from "@/lib/api"
import { useAppStore } from "@/stores/app-store"

const bucketConfig = [
  { key: "buyable", title: "可买候选", icon: CheckCircle2, tone: "text-green-600" },
  { key: "wait_for_pullback", title: "等回调", icon: Clock3, tone: "text-amber-600" },
  { key: "mean_reversion_watch", title: "均值回归观察", icon: RefreshCw, tone: "text-blue-600" },
  { key: "watch_only", title: "只观察", icon: Eye, tone: "text-muted-foreground" },
  { key: "excluded", title: "剔除", icon: ShieldAlert, tone: "text-red-600" },
]

function formatNumber(value: unknown, digits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--"
  return value.toFixed(digits)
}

function healthText(data?: ScreeningRunResponse) {
  const status = data?.data_health?.overall_status || "unknown"
  const qlibLast = data?.data_health?.sources?.qlib?.last_date || "--"
  const stocksLast = data?.data_health?.sources?.stocks?.last_date || "--"
  return { status, qlibLast, stocksLast }
}

function CandidateTable({ candidates }: { candidates: ScreeningCandidate[] }) {
  if (!candidates.length) {
    return <div className="py-6 text-center text-sm text-muted-foreground">暂无候选</div>
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>标的</TableHead>
          <TableHead className="text-right">RSI</TableHead>
          <TableHead className="text-right">布林位置</TableHead>
          <TableHead>信号</TableHead>
          <TableHead className="text-right">因子分</TableHead>
          <TableHead className="text-right">AI策略分</TableHead>
          <TableHead>动作</TableHead>
          <TableHead>理由</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {candidates.map((item) => (
          <TableRow key={item.code}>
            <TableCell>
              <div className="font-medium">{item.name || item.code}</div>
              <div className="text-xs text-muted-foreground">{item.code}</div>
            </TableCell>
            <TableCell className="text-right">
              {formatNumber(item.mean_reversion?.rsi, 1)}
            </TableCell>
            <TableCell className="text-right">
              {formatNumber(
                typeof item.mean_reversion?.bollingerPosition === "number"
                  ? item.mean_reversion.bollingerPosition * 100
                  : undefined,
                0,
              )}
              {typeof item.mean_reversion?.bollingerPosition === "number" ? "%" : ""}
            </TableCell>
            <TableCell>
              <Badge variant="outline">{item.mean_reversion?.signal || "暂无"}</Badge>
            </TableCell>
            <TableCell className="text-right">
              {typeof item.factor_signal?.score === "number" ? (
                <div className="space-y-1">
                  <Badge variant={item.factor_signal.score >= 0 ? "default" : "secondary"}>
                    {item.factor_signal.score.toFixed(2)}
                  </Badge>
                  {item.factor_signal.rank ? (
                    <div className="text-xs text-muted-foreground">#{item.factor_signal.rank}</div>
                  ) : null}
                </div>
              ) : (
                <span className="text-muted-foreground">--</span>
              )}
            </TableCell>
            <TableCell className="text-right">
              {typeof item.ai_strategy?.score === "number" ? (
                <div className="space-y-1">
                  <Badge variant={item.ai_strategy.score >= 65 ? "default" : "secondary"}>
                    {item.ai_strategy.score.toFixed(0)}
                  </Badge>
                  <div className="text-xs text-muted-foreground">
                    {item.ai_strategy.recommendation || "--"}
                  </div>
                </div>
              ) : (
                <span className="text-muted-foreground">--</span>
              )}
            </TableCell>
            <TableCell>
              <Badge variant={item.action === "降级" ? "secondary" : "default"}>
                {item.action}
              </Badge>
            </TableCell>
            <TableCell className="max-w-[360px] text-sm text-muted-foreground">
              {item.reason || item.warning || "暂无说明"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function ScreeningWorkflowPage() {
  const aiStrategyParams = useAppStore((state) => state.aiStrategyParams)
  const generatedStrategy = aiStrategyParams.backtestDraft
    ? { params: aiStrategyParams.backtestDraft.params }
    : undefined
  const mutation = useMutation({
    mutationFn: () => api.screening.run(generatedStrategy ? { generated_strategy: generatedStrategy } : undefined),
  })
  const reportQuery = useQuery({
    queryKey: ["screening", "report"],
    queryFn: () => api.screening.report(),
    refetchInterval: 120_000,
  })

  const data = mutation.data
  const report = reportQuery.data

  const openTradePlan = () => {
    const codes = Object.values(data?.buckets || {})
      .flat()
      .map((candidate: any) => candidate.code)
      .filter(Boolean)
      .slice(0, 20)
      .join(",")
    if (codes) {
      window.location.href = `/trade-plan?codes=${encodeURIComponent(codes)}`
    } else {
      window.location.href = "/trade-plan"
    }
  }
  const health = healthText(data)
  const bucketCounts = useMemo(() => {
    return bucketConfig.map((bucket) => ({
      ...bucket,
      count: data?.buckets?.[bucket.key]?.length || 0,
    }))
  }, [data])

  return (
    <div className="mx-auto max-w-[1400px] space-y-4 p-4 md:space-y-6 md:p-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="space-y-1">
          <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight md:text-2xl">
            <ListChecks className="h-7 w-7 text-primary" />
            盘后选股
          </h1>
          <p className="text-sm text-muted-foreground">
            默认从最新智能股票池 TopN 取候选；本地 bin 算均值回归（异步任务，不再受 90 秒 HTTP 超时限制）。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                正在运行
              </>
            ) : (
              <>
                <RefreshCw className="mr-2 h-4 w-4" />
                运行盘后选股
              </>
            )}
          </Button>
          <Button variant="outline" onClick={openTradePlan} disabled={!data}>
            生成交易计划
          </Button>
        </div>
      </div>

      {mutation.isError && (
        <div className="flex items-start gap-2 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-300">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{mutation.error instanceof Error ? mutation.error.message : "运行失败"}</span>
        </div>
      )}

      {generatedStrategy && (
        <div className="rounded-md border border-blue-500/30 bg-blue-500/10 p-3 text-sm text-blue-700 dark:text-blue-300">
          已纳入AI生成策略：本轮盘后选股会把最近一次“用此策略跑回测”的策略参数作为辅助决策依据。
        </div>
      )}

      {data?.candidate_source && (
        <div className="rounded-md border border-border bg-muted/40 p-3 text-sm">
          <span className="font-medium">候选来源：</span>
          {data.candidate_source.source === "stock_pool" && (
            <span>
              股票池「{data.candidate_source.pool_name}」Top{data.candidate_source.count}
              （刷新日 {data.candidate_source.as_of}）
            </span>
          )}
          {data.candidate_source.source === "request" && <span>请求指定名单</span>}
          {data.candidate_source.source === "hardcoded_fallback" && (
            <span className="text-amber-700 dark:text-amber-300">
              硬编码兜底（请先刷新智能股票池）
            </span>
          )}
          {data.trading_allowed === false && (
            <span className="ml-2 text-red-600">· 当前禁止新开仓信号</span>
          )}
        </div>
      )}

      {(data?.circuit_breaker?.active || report?.circuit_breaker_active) && (
        <div className="flex items-start gap-2 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-300">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            熔断已触发：近 3 期推荐 T+5 胜率偏低，buyable 已清空。建议暂停新开仓，进入观察期。
          </span>
        </div>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">信号回验（T+5）</CardTitle>
          <CardDescription>基于历史盘后推荐落库结果的滚动绩效，胜率与收益分开统计</CardDescription>
        </CardHeader>
        <CardContent>
          {reportQuery.isLoading ? (
            <div className="text-sm text-muted-foreground">加载回验中…</div>
          ) : report?.status === "available" ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
              <div>
                <div className="text-muted-foreground">近20期胜率</div>
                <div className="text-lg font-semibold">
                  {typeof report.rolling_20_win_rate === "number"
                    ? `${(report.rolling_20_win_rate * 100).toFixed(1)}%`
                    : "--"}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground">近20期 T+5 均收益</div>
                <div className="text-lg font-semibold">
                  {typeof report.rolling_20_avg_t5_return === "number"
                    ? `${(report.rolling_20_avg_t5_return * 100).toFixed(2)}%`
                    : "--"}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground">近3期胜率</div>
                <div className="text-lg font-semibold">
                  {typeof report.recent_3_win_rate === "number"
                    ? `${(report.recent_3_win_rate * 100).toFixed(1)}%`
                    : "--"}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground">建议</div>
                <div className="text-lg font-semibold">
                  {report.suggestion === "defensive"
                    ? "防守/暂停"
                    : report.suggestion === "cautious"
                      ? "谨慎"
                      : "正常"}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">
              {report?.message === "no_screening_history"
                ? "暂无筛选历史。请先运行盘后选股并等待 T+5 后回验。"
                : report?.message || "回验数据不足"}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">数据状态</CardTitle>
            <CardDescription>Qlib {health.qlibLast}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{health.status}</div>
            <p className="text-xs text-muted-foreground">股票数据 {health.stocksLast}</p>
          </CardContent>
        </Card>
        {bucketCounts.slice(0, 3).map((bucket) => {
          const Icon = bucket.icon
          return (
            <Card key={bucket.key}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium">
                  <Icon className={`h-4 w-4 ${bucket.tone}`} />
                  {bucket.title}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{bucket.count}</div>
                <p className="text-xs text-muted-foreground">本轮候选分桶</p>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="grid gap-4 xl:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>热点板块</CardTitle>
            <CardDescription>按现有热点模块取前 5 项</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {(data?.hot_sectors || []).slice(0, 5).map((sector) => (
              <div key={String(sector.name)} className="flex items-center justify-between text-sm">
                <span>{sector.name}</span>
                <Badge variant="outline">{formatNumber(sector.change_pct)}%</Badge>
              </div>
            ))}
            {!data && <div className="text-sm text-muted-foreground">运行后显示</div>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>ETF 信号</CardTitle>
            <CardDescription>优先展示 buy 或涨幅靠前 ETF</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {(data?.etf_signals || []).slice(0, 5).map((etf) => (
              <div key={String(etf.code)} className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate">{etf.name || etf.code}</span>
                <Badge variant={etf.signal === "buy" ? "default" : "outline"}>{etf.signal || "hold"}</Badge>
              </div>
            ))}
            {!data && <div className="text-sm text-muted-foreground">运行后显示</div>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>因子链路</CardTitle>
            <CardDescription>
              {data?.factor_summary?.status === "available"
                ? `${data.factor_summary.start_date} ~ ${data.factor_summary.end_date}`
                : "读取最近一次因子分析"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">最佳因子</span>
              <span>{data?.factor_summary?.best_factor || "--"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">最大 IC</span>
              <span>{formatNumber(data?.factor_summary?.best_ic, 3)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">有效因子</span>
              <span>{data?.factor_summary?.effective_factors || "--"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">AI策略均分</span>
              <span>{formatNumber(data?.ai_strategy_summary?.average_score, 1)}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>风险摘要</CardTitle>
            <CardDescription>近期窗口的组合代理指标</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Sharpe</span>
              <span>{formatNumber(data?.risk_summary?.metrics?.sharpe_ratio)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">最大回撤</span>
              <span>{formatNumber((data?.risk_summary?.metrics?.max_drawdown || 0) * 100)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">风险等级</span>
              <span>{data?.risk_summary?.position_sizing?.risk_level || "--"}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {data?.warnings?.length ? (
        <div className="rounded-md border border-yellow-500/40 bg-yellow-500/10 p-3 text-sm text-yellow-700 dark:text-yellow-300">
          {data.warnings.map((warning) => (
            <div key={warning} className="flex items-start gap-2">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{warning}</span>
            </div>
          ))}
        </div>
      ) : null}

      <div className="space-y-4">
        {bucketConfig.map((bucket) => {
          const Icon = bucket.icon
          const candidates = data?.buckets?.[bucket.key] || []
          return (
            <Card key={bucket.key}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Icon className={`h-5 w-5 ${bucket.tone}`} />
                  {bucket.title}
                  <Badge variant="outline">{candidates.length}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <CandidateTable candidates={candidates} />
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
