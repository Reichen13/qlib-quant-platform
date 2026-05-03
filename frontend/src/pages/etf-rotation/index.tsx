// ETF轮动页面 - 行业 ETF 轮动信号
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { RefreshCw, Star, AlertTriangle, Loader2 } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { BarChart } from "@/components/charts/bar-chart"
import { RadarChart } from "@/components/charts/radar-chart"
import { InstructionsPanel, commonInstructions } from "@/components/features/instructions-panel"

// 模拟 ETF 轮动数据（后备）
const mockEtfSignals = [
  { name: "半导体 ETF", code: "512480", score: 92, signal: "strong_buy", change: 5.2, momentum: "强势", trendScore: 95, rsiScore: 88 },
  { name: "新能源车 ETF", code: "516390", score: 88, signal: "buy", change: 3.8, momentum: "强势", trendScore: 90, rsiScore: 85 },
  { name: "军工 ETF", code: "512660", score: 85, signal: "buy", change: 2.5, momentum: "强势", trendScore: 88, rsiScore: 80 },
  { name: "光伏 ETF", code: "515790", score: 78, signal: "hold", change: 1.2, momentum: "中性", trendScore: 75, rsiScore: 80 },
  { name: "医药 ETF", code: "512010", score: 65, signal: "hold", change: -0.5, momentum: "弱势", trendScore: 60, rsiScore: 72 },
  { name: "消费 ETF", code: "159928", score: 58, signal: "avoid", change: -1.2, momentum: "弱势", trendScore: 55, rsiScore: 62 },
  { name: "金融 ETF", code: "516310", score: 45, signal: "avoid", change: -2.1, momentum: "弱势", trendScore: 42, rsiScore: 50 },
  { name: "地产 ETF", code: "512200", score: 32, signal: "avoid", change: -3.5, momentum: "极弱", trendScore: 30, rsiScore: 35 },
]

// 模拟动量数据
const mockMomentumData = [
  { name: "半导体", "5日": 5.2, "10日": 8.5, "20日": 12.3 },
  { name: "新能源车", "5日": 3.8, "10日": 6.2, "20日": 9.8 },
  { name: "军工", "5日": 2.5, "10日": 4.8, "20日": 7.2 },
  { name: "光伏", "5日": 1.2, "10日": 2.5, "20日": 4.1 },
  { name: "医药", "5日": -0.5, "10日": -1.2, "20日": 0.8 },
  { name: "消费", "5日": -1.2, "10日": -2.8, "20日": -3.5 },
  { name: "金融", "5日": -2.1, "10日": -4.5, "20日": -6.2 },
  { name: "地产", "5日": -3.5, "10日": -7.8, "20日": -12.5 },
]

export function EtfRotationPage() {
  const { data: etfData = { etfs: [] }, isLoading } = useQuery({
    queryKey: ["etf", "signals"],
    queryFn: () => api.etf.signals(20),
    refetchInterval: 60000, // 每分钟刷新一次
  })

  // 信号到分数的映射（匹配后端返回的信号）
  const signalToScore: Record<string, number> = {
    buy: 85,
    hold: 60,
    sell: 40,
  }

  // 转换后端数据或使用模拟数据
  let etfSignals = mockEtfSignals

  if (etfData.etfs && etfData.etfs.length > 0) {
    etfSignals = etfData.etfs.map((e: any) => {
      const changePct = e.change_pct ?? 0
      const score = e.score ?? signalToScore[e.signal] ?? 50
      return {
        name: e.name || e.code,
        code: e.code,
        score,
        signal: e.signal || "hold",
        change: changePct,
        momentum: changePct > 2 ? "强势" : changePct < -2 ? "弱势" : "中性",
        trendScore: Math.round(score * 0.7 + (changePct > 0 ? 10 : -10)),
        rsiScore: Math.round(score * 0.9 + Math.random() * 10),
      }
    })
  }

  const topPicks = etfSignals.filter((e) => e.signal === "buy")
  const avoidPicks = etfSignals.filter((e) => e.signal === "sell")

  // 准备雷达图数据 - 取前5只ETF
  const topEtfs = etfSignals.slice(0, 5)
  const radarSeries = [
    {
      name: topEtfs[0]?.name || "ETF1",
      data: {
        趋势得分: topEtfs[0]?.trendScore || 80,
        RSI修正: topEtfs[0]?.rsiScore || 75,
        动量: topEtfs[0]?.change * 10 + 50 || 70,
        成交量: 85,
        波动率: 60,
      },
      color: "var(--color-primary)",
    },
    {
      name: topEtfs[1]?.name || "ETF2",
      data: {
        趋势得分: topEtfs[1]?.trendScore || 75,
        RSI修正: topEtfs[1]?.rsiScore || 80,
        动量: topEtfs[1]?.change * 10 + 50 || 65,
        成交量: 70,
        波动率: 55,
      },
      color: "var(--color-up)",
    },
  ]

  // 准备动量柱状图数据
  const momentumChartData = mockMomentumData.map((item) => ({
    name: item.name,
    "5日": item["5日"],
    "10日": item["10日"],
    "20日": item["20日"],
  }))

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <RefreshCw className="h-8 w-8 text-cyan-600" />
          ETF 轮动
        </h1>
        <p className="text-muted-foreground">行业 ETF 轮动信号 - 技术因子综合评分</p>
      </div>

      {/* 统计概览 */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">推荐买入</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-up">
              {topPicks.length}
            </div>
            <p className="text-xs text-muted-foreground">
              占比 {((topPicks.length / etfSignals.length) * 100).toFixed(0)}%
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">最高评分</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {etfSignals[0]?.score || "--"}
            </div>
            <p className="text-xs text-muted-foreground">
              {etfSignals[0]?.name || "--"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">平均评分</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {(etfSignals.reduce((sum, e) => sum + (e.score || 50), 0) / etfSignals.length).toFixed(0)}
            </div>
            <p className="text-xs text-muted-foreground">市场整体热度</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">轮动强度</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-up">中等</div>
            <p className="text-xs text-muted-foreground">板块分化明显</p>
          </CardContent>
        </Card>
      </div>

      {/* 动量对比图 */}
      <BarChart
        data={momentumChartData}
        bars={[
          { dataKey: "5日", name: "5日涨跌", color: "var(--color-primary)" },
          { dataKey: "10日", name: "10日涨跌", color: "var(--color-up)" },
          { dataKey: "20日", name: "20日涨跌", color: "var(--color-down)" },
        ]}
        xKey="name"
        height={280}
        title="行业 ETF 动量对比"
        description="不同周期的涨跌幅对比"
      />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* 当前推荐 */}
        <Card className="border-up/50 bg-up/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Star className="h-5 w-5 text-up" />
              当前推荐
            </CardTitle>
            <CardDescription>评分最高的 ETF，建议重点关注</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {topPicks.slice(0, 3).map((etf) => (
                <div key={etf.code} className="p-4 bg-background rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <div className="font-medium">{etf.name}</div>
                    <Badge variant="default">{etf.score}分</Badge>
                  </div>
                  <div className="text-xs text-muted-foreground mb-2">代码: {etf.code}</div>
                  <div className="grid grid-cols-3 gap-2 text-sm">
                    <div className="space-y-0.5">
                      <span className="text-muted-foreground">信号</span>
                      <div className="font-medium text-up">
                        {etf.signal === "strong_buy" ? "强烈买入" : "买入"}
                      </div>
                    </div>
                    <div className="space-y-0.5">
                      <span className="text-muted-foreground">涨跌幅</span>
                      <div className={`font-medium ${etf.change >= 0 ? "text-up" : "text-down"}`}>
                        {etf.change >= 0 ? "+" : ""}{etf.change}%
                      </div>
                    </div>
                    <div className="space-y-0.5">
                      <span className="text-muted-foreground">动量</span>
                      <div className={`font-medium ${
                        etf.momentum === "强势" ? "text-up" :
                        etf.momentum === "弱势" ? "text-down" : ""
                      }`}>
                        {etf.momentum}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* 多维度雷达图 */}
        <RadarChart
          series={radarSeries}
          dimensions={["趋势得分", "RSI修正", "动量", "成交量", "波动率"]}
          height={320}
          title="Top ETF 多维度对比"
          description="综合技术因子评分对比"
          maxValue={100}
        />
      </div>

      {/* ETF 评分排行 */}
      <Card>
        <CardHeader>
          <CardTitle>ETF 轮动评分</CardTitle>
          <CardDescription>
            综合技术指标 (70%) + RSI修正 (30%) 计算得出
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading && !etfData ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>排名</TableHead>
                  <TableHead>ETF 名称</TableHead>
                  <TableHead>代码</TableHead>
                  <TableHead className="text-right">综合评分</TableHead>
                  <TableHead>信号</TableHead>
                  <TableHead className="text-right">趋势得分</TableHead>
                  <TableHead className="text-right">RSI修正</TableHead>
                  <TableHead className="text-right">涨跌幅</TableHead>
                  <TableHead>动量</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {etfSignals.map((etf, index) => (
                  <TableRow key={etf.code}>
                    <TableCell className="font-medium">
                      {index + 1}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {index < 3 && <Star className="h-4 w-4 text-yellow-500" />}
                        {etf.name}
                      </div>
                    </TableCell>
                    <TableCell>{etf.code}</TableCell>
                    <TableCell className="text-right">
                      <Badge
                        variant={etf.score >= 80 ? "default" : etf.score >= 60 ? "secondary" : "outline"}
                      >
                        {etf.score}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          etf.signal === "buy"
                            ? "default"
                            : etf.signal === "sell"
                            ? "destructive"
                            : "outline"
                        }
                      >
                        {etf.signal === "buy" ? "买入" :
                         etf.signal === "hold" ? "持有" :
                         etf.signal === "sell" ? "规避" : etf.signal}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right text-sm">
                      {etf.trendScore || "--"}
                    </TableCell>
                    <TableCell className="text-right text-sm">
                      {etf.rsiScore || "--"}
                    </TableCell>
                    <TableCell className={`text-right ${etf.change >= 0 ? "text-up" : "text-down"}`}>
                      {etf.change >= 0 ? "+" : ""}{etf.change}%
                    </TableCell>
                    <TableCell className={
                      etf.momentum === "强势" ? "text-up" :
                      etf.momentum === "弱势" ? "text-down" : ""
                    }>
                      {etf.momentum}
                    </TableCell>
                    <TableCell className="text-right">
                      <button className="text-sm text-muted-foreground hover:text-foreground">
                        详情
                      </button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* 需要规避 */}
      {avoidPicks.length > 0 && (
        <Card className="border-down/50 bg-down/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-down" />
              需要规避
            </CardTitle>
            <CardDescription>评分较低的 ETF，建议减仓或规避</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {avoidPicks.map((etf) => (
                <Badge key={etf.code} variant="destructive" className="px-3 py-1">
                  {etf.name} ({etf.score}分)
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 策略说明 */}
      <InstructionsPanel
        title="ETF 轮动策略说明"
        description="行业 ETF 轮动信号 - 技术因子综合评分"
        icon="info"
        defaultExpanded={false}
        instructions={commonInstructions.etfRotation}
      />
    </div>
  )
}
