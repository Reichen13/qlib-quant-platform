// 新闻分析页面 - 市场情报与情感分析
import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { Newspaper, Search, TrendingUp, TrendingDown, Minus, Loader2, ExternalLink } from "lucide-react"

function SentimentBadge({ score, label }: { score: number; label: string }) {
  const color = label === "positive"
    ? "bg-emerald-100 text-emerald-700 border-emerald-200"
    : label === "negative"
    ? "bg-red-100 text-red-700 border-red-200"
    : "bg-slate-100 text-slate-600 border-slate-200"

  const icon = label === "positive"
    ? <TrendingUp className="h-3 w-3" />
    : label === "negative"
    ? <TrendingDown className="h-3 w-3" />
    : <Minus className="h-3 w-3" />

  return (
    <Badge variant="outline" className={`flex items-center gap-1 text-xs ${color}`}>
      {icon}
      <span>{score > 0 ? "+" : ""}{score.toFixed(2)}</span>
    </Badge>
  )
}

function SentimentBar({ positive, negative, neutral }: { positive: number; negative: number; neutral: number }) {
  const total = positive + negative + neutral || 1
  const posPct = (positive / total) * 100
  const negPct = (negative / total) * 100
  const neuPct = (neutral / total) * 100

  return (
    <div className="flex h-2 rounded-full overflow-hidden bg-muted">
      <div className="bg-emerald-500 transition-all" style={{ width: `${posPct}%` }} />
      <div className="bg-slate-300 transition-all" style={{ width: `${neuPct}%` }} />
      <div className="bg-red-500 transition-all" style={{ width: `${negPct}%` }} />
    </div>
  )
}

export function NewsAnalysisPage() {
  const [searchCode, setSearchCode] = useState("")
  const [activeCode, setActiveCode] = useState("")

  const handleSearch = () => {
    const trimmed = searchCode.trim()
    if (trimmed) {
      setActiveCode(trimmed)
    }
  }

  // 每日简报
  const { data: brief, isLoading: briefLoading } = useQuery({
    queryKey: ["news", "daily-brief"],
    queryFn: () => api.news.dailyBrief(),
    staleTime: 5 * 60 * 1000,
  })

  // 全市场情感
  const { data: marketSentiment } = useQuery({
    queryKey: ["news", "market-sentiment"],
    queryFn: () => api.news.marketSentiment(),
    staleTime: 5 * 60 * 1000,
  })

  // 单股新闻
  const { data: stockNews, isLoading: stockNewsLoading } = useQuery({
    queryKey: ["news", "sentiment", activeCode],
    queryFn: () => api.news.sentiment(activeCode),
    enabled: !!activeCode,
    staleTime: 2 * 60 * 1000,
  })

  // 单股事件
  const { data: stockEvents } = useQuery({
    queryKey: ["news", "events", activeCode],
    queryFn: () => api.news.events(activeCode),
    enabled: !!activeCode,
    staleTime: 5 * 60 * 1000,
  })

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Newspaper className="h-8 w-8 text-slate-600" />
          新闻分析
        </h1>
        <p className="text-muted-foreground">市场情报、情感分析与事件提取</p>
      </div>

      {/* 每日简报 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            每日市场简报
            {briefLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </CardTitle>
          <CardDescription>{brief?.date || "--"}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm leading-relaxed">{brief?.summary || "加载中..."}</p>
          {brief?.sentiment && (
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">市场情绪:</span>
              <SentimentBadge score={brief.sentiment.score} label={brief.sentiment.label} />
              <span className="text-xs text-muted-foreground">
                {brief.total || 0} 条新闻
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 市场情感热力 */}
      {marketSentiment?.sectors && marketSentiment.sectors.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">行业情感分布</CardTitle>
            <CardDescription>今日市场新闻的行业情感热力</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
              {marketSentiment.sectors.slice(0, 8).map((s: any) => (
                <div key={s.name} className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                  <div className="space-y-1 min-w-0">
                    <p className="text-sm font-medium truncate">{s.name}</p>
                    <p className="text-xs text-muted-foreground">{s.count} 条</p>
                  </div>
                  <SentimentBadge score={s.score} label={s.score > 0.15 ? "positive" : s.score < -0.15 ? "negative" : "neutral"} />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 股票新闻搜索 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">个股新闻搜索</CardTitle>
          <CardDescription>输入股票代码查询相关新闻与情感分析</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Input
              placeholder="输入代码如 600519.SS 或 SH600519"
              value={searchCode}
              onChange={(e) => setSearchCode(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              className="max-w-sm font-mono"
            />
            <Button onClick={handleSearch} disabled={stockNewsLoading}>
              {stockNewsLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              <span className="ml-2">搜索</span>
            </Button>
          </div>

          {/* 搜索结果 */}
          {activeCode && stockNews && (
            <div className="space-y-4">
              {/* 摘要 */}
              <div className="flex items-center gap-4 p-3 bg-muted/30 rounded-lg">
                <div className="space-y-1">
                  <p className="text-sm font-medium">{activeCode}</p>
                  <p className="text-xs text-muted-foreground">
                    {stockNews.total} 条相关新闻
                  </p>
                </div>
                <div className="ml-auto flex items-center gap-3">
                  <div className="text-right">
                    <p className="text-xs text-muted-foreground">情感均分</p>
                    <p className="text-sm font-bold">
                      {(stockNews.avg_sentiment_score ?? 0) > 0 ? "+" : ""}
                      {(stockNews.avg_sentiment_score ?? 0).toFixed(2)}
                    </p>
                  </div>
                  <SentimentBar
                    positive={stockNews.positive_count || 0}
                    negative={stockNews.negative_count || 0}
                    neutral={stockNews.neutral_count || 0}
                  />
                </div>
              </div>

              {/* 新闻列表 */}
              <div className="space-y-2">
                {(stockNews.news || []).map((item: any, i: number) => (
                  <div
                    key={i}
                    className="flex items-start gap-3 p-3 bg-muted/30 rounded-lg hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex-1 min-w-0 space-y-1">
                      <p className="text-sm leading-snug">
                        {item.url ? (
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="hover:text-primary transition-colors inline-flex items-start gap-1"
                          >
                            {item.title}
                            <ExternalLink className="h-3 w-3 shrink-0 mt-0.5 text-muted-foreground" />
                          </a>
                        ) : (
                          item.title
                        )}
                      </p>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span>{item.source}</span>
                        <span>·</span>
                        <span>{item.time}</span>
                      </div>
                    </div>
                    {item.sentiment && (
                      <SentimentBadge score={item.sentiment.score} label={item.sentiment.label} />
                    )}
                  </div>
                ))}
              </div>

              {/* 结构化事件 */}
              {stockEvents?.events && stockEvents.events.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-sm font-medium">结构化事件</h4>
                  <div className="grid gap-2">
                    {stockEvents.events.map((evt: any, i: number) => (
                      <div key={i} className="flex items-center gap-3 p-2 bg-muted/30 rounded-lg">
                        <Badge variant="outline" className="text-xs shrink-0">
                          {evt.type}
                        </Badge>
                        <p className="text-sm flex-1 truncate">{evt.summary}</p>
                        <SentimentBadge score={0} label={evt.impact || "neutral"} />
                        <span className="text-xs text-muted-foreground">{evt.date}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeCode && !stockNews && !stockNewsLoading && (
            <p className="text-sm text-muted-foreground text-center py-8">输入代码后点击搜索查看相关新闻</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
