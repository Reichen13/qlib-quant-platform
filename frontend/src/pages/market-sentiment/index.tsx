import { useState, useEffect } from "react";
import { Gauge, TrendingUp, TrendingDown, AlertTriangle, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface SentimentData {
  score: number; sentiment: string; updated: string;
  dimensions: Record<string, any>; warnings?: string[];
}

function ScoreGauge({ score, sentiment }: { score: number; sentiment: string }) {
  const bg = score > 65 ? "bg-red-500" : score < 35 ? "bg-green-500" : "bg-amber-500";
  return (
    <div className="text-center">
      <div className={`text-4xl font-bold ${score > 65 ? "text-red-500" : score < 35 ? "text-green-500" : "text-amber-500"}`}>{score}</div>
      <div className={`text-sm ${score > 65 ? "text-red-500" : score < 35 ? "text-green-500" : "text-amber-500"}`}>{sentiment}</div>
      <div className="w-full bg-muted h-2 rounded mt-2">
        <div className={`${bg} h-2 rounded transition-all`} style={{ width: `${score}%` }} />
      </div>
      <div className="flex justify-between text-xs text-muted-foreground mt-1">
        <span>0 恐慌</span><span>50 中性</span><span>100 亢奋</span>
      </div>
    </div>
  );
}

function MiniBar({ label, value }: { label: string; value: number }) {
  const absVal = Math.abs(value);
  return (
    <div className="flex items-center justify-between text-xs py-0.5">
      <span className="truncate max-w-[100px]">{label}</span>
      <span className={value >= 0 ? "text-red-500" : "text-green-500"}>{value >= 0 ? "+" : ""}{value.toFixed(1)}%</span>
      <div className="w-16 bg-muted h-1.5 rounded ml-2">
        <div className={`${value >= 0 ? "bg-red-500" : "bg-green-500"} h-1.5 rounded`}
          style={{ width: `${Math.min(absVal * 5, 100)}%` }} />
      </div>
    </div>
  );
}

export function MarketSentimentPage() {
  const [data, setData] = useState<SentimentData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/sentiment/overview")
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="p-6 flex items-center justify-center h-64">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  );

  if (!data) return (
    <div className="p-6 text-center text-muted-foreground">无法加载市场情绪数据</div>
  );

  const d = data.dimensions;

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Gauge className="h-6 w-6 text-purple-600" /> 市场情绪
          </h1>
          <p className="text-muted-foreground text-sm">多维度市场温度计 · 更新于 {data.updated}</p>
        </div>
        <ScoreGauge score={data.score} sentiment={data.sentiment} />
      </div>

      {data.warnings && data.warnings.length > 0 && (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="pt-3 text-sm text-amber-800 flex gap-2">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>{data.warnings.join(" / ")}</span>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* 核心指数 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">核心指数</CardTitle>
          </CardHeader>
          <CardContent>
            {d.indices?.data?.length > 0 ? d.indices.data.map((idx: any, i: number) => (
              <div key={i} className="flex justify-between items-center py-1 text-sm">
                <span className="text-muted-foreground">{idx.name}</span>
                <div className="flex items-center gap-2">
                  <span className="font-mono">{idx.price.toFixed(1)}</span>
                  <span className={idx.change_pct >= 0 ? "text-red-500" : "text-green-500"}>
                    {idx.change_pct >= 0 ? "+" : ""}{idx.change_pct.toFixed(2)}%
                  </span>
                </div>
              </div>
            )) : <p className="text-sm text-muted-foreground">暂不可用</p>}
          </CardContent>
        </Card>

        {/* 北向资金 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">北向资金</CardTitle>
          </CardHeader>
          <CardContent>
            {d.northbound?.status === "unavailable" ? (
              <p className="text-sm text-muted-foreground">暂不可用</p>
            ) : (
              <>
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-muted-foreground">近5日净流入</span>
                  <span className={d.northbound?.net_flow_5d >= 0 ? "text-red-500 font-bold" : "text-green-500 font-bold"}>
                    {d.northbound?.net_flow_5d >= 0 ? "+" : ""}{d.northbound?.net_flow_5d} 亿
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">近20日净流入</span>
                  <span className={d.northbound?.net_flow_20d >= 0 ? "text-red-500" : "text-green-500"}>
                    {d.northbound?.net_flow_20d >= 0 ? "+" : ""}{d.northbound?.net_flow_20d} 亿
                  </span>
                </div>
                <Badge variant="outline" className={`mt-2 text-xs ${d.northbound?.status === "inflow" ? "border-red-200 text-red-600" : "border-green-200 text-green-600"}`}>
                  {d.northbound?.status === "inflow" ? "持续流入" : d.northbound?.status === "outflow" ? "持续流出" : "中性"}
                </Badge>
              </>
            )}
          </CardContent>
        </Card>

        {/* 龙虎榜 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">龙虎榜 TOP 净买入</CardTitle>
          </CardHeader>
          <CardContent>
            {d.dragon_tiger?.status === "active" ? (
              d.dragon_tiger.top_net_buy?.slice(0, 5).map((item: [string, number], i: number) => (
                <div key={i} className="flex justify-between text-xs py-0.5">
                  <span>{item[0]}</span>
                  <span className="text-red-500">{item[1] > 0 ? "+" : ""}{item[1]}万</span>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">暂无数据</p>
            )}
          </CardContent>
        </Card>

        {/* 行业板块 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1">
              <TrendingUp className="h-3 w-3 text-red-500" /> 领涨行业
            </CardTitle>
          </CardHeader>
          <CardContent>
            {d.sectors?.top?.length > 0 ? d.sectors.top.map((s: any, i: number) => (
              <MiniBar key={i} label={s.industry || s.name} value={s.change_pct} />
            )) : <p className="text-sm text-muted-foreground">暂无</p>}
            {d.sectors?.bottom?.length > 0 && (
              <>
                <CardTitle className="text-sm mt-3 mb-1 flex items-center gap-1">
                  <TrendingDown className="h-3 w-3 text-green-500" /> 领跌行业
                </CardTitle>
                {d.sectors.bottom.map((s: any, i: number) => (
                  <MiniBar key={i} label={s.industry || s.name} value={s.change_pct} />
                ))}
              </>
            )}
          </CardContent>
        </Card>

        {/* 概念板块 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">热门概念</CardTitle>
          </CardHeader>
          <CardContent>
            {d.hot_boards?.boards?.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {d.hot_boards.boards.slice(0, 8).map((b: any, i: number) => (
                  <Badge key={i} variant="outline" className="text-xs">
                    {b.name}
                    <span className={`ml-1 ${b.change_pct >= 0 ? "text-red-500" : "text-green-500"}`}>
                      {b.change_pct >= 0 ? "+" : ""}{b.change_pct}%
                    </span>
                  </Badge>
                ))}
              </div>
            ) : <p className="text-sm text-muted-foreground">暂无数据</p>}
          </CardContent>
        </Card>

        {/* 解禁预警 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1">
              <AlertTriangle className="h-3 w-3 text-amber-500" /> 解禁预警
            </CardTitle>
          </CardHeader>
          <CardContent>
            {d.unlock?.items?.length > 0 ? d.unlock.items.slice(0, 5).map((u: any, i: number) => (
              <div key={i} className="flex justify-between text-xs py-0.5">
                <span>{u.name}</span>
                <span className="text-muted-foreground">{u.market_cap} · {u.date}</span>
              </div>
            )) : <p className="text-sm text-muted-foreground">近期无大规模解禁</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
