// 配对交易页面 - 统计套利策略
import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Link2, Loader2, Activity } from "lucide-react"
import { LineChartComponent } from "@/components/charts/line-chart"
import { InstructionsPanel, commonInstructions } from "@/components/features/instructions-panel"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"

// 预设配对对
const defaultPairs = [
  {
    pair: "招商银行 / 平安银行",
    stock1: "600036.SH",
    stock2: "000001.SZ",
    category: "银行",
    correlation: 0.92,
    pValue: 0.001,
    zScore: 2.35,
    signal: "做空价差",
    status: "开仓机会",
  },
  {
    pair: "贵州茅台 / 五粮液",
    stock1: "600519.SH",
    stock2: "000858.SZ",
    category: "白酒",
    correlation: 0.88,
    pValue: 0.005,
    zScore: -1.85,
    signal: "做多价差",
    status: "观察中",
  },
  {
    pair: "中国平安 / 中国人寿",
    stock1: "601318.SH",
    stock2: "601628.SH",
    category: "保险",
    correlation: 0.85,
    pValue: 0.008,
    zScore: 0.45,
    signal: "中性",
    status: "正常",
  },
  {
    pair: "万科A / 保利发展",
    stock1: "000002.SZ",
    stock2: "600048.SH",
    category: "地产",
    correlation: 0.81,
    pValue: 0.012,
    zScore: -2.12,
    signal: "做多价差",
    status: "开仓机会",
  },
  {
    pair: "美的集团 / 格力电器",
    stock1: "000333.SZ",
    stock2: "000651.SZ",
    category: "家电",
    correlation: 0.79,
    pValue: 0.015,
    zScore: 1.05,
    signal: "中性",
    status: "正常",
  },
  {
    pair: "伊利股份 / 光明乳业",
    stock1: "600887.SH",
    stock2: "600597.SH",
    category: "食品",
    correlation: 0.76,
    pValue: 0.020,
    zScore: -0.85,
    signal: "中性",
    status: "正常",
  },
  {
    pair: "比亚迪 / 长城汽车",
    stock1: "002594.SZ",
    stock2: "601633.SH",
    category: "汽车",
    correlation: 0.72,
    pValue: 0.035,
    zScore: 0.65,
    signal: "中性",
    status: "观察中",
  },
]

// 模拟价差数据
const mockSpreadData = [
  { date: "2024-01", spread: 1.0, upper: 2, lower: -2 },
  { date: "2024-02", spread: 1.2, upper: 2, lower: -2 },
  { date: "2024-03", spread: 0.8, upper: 2, lower: -2 },
  { date: "2024-04", spread: 1.5, upper: 2, lower: -2 },
  { date: "2024-05", spread: 2.2, upper: 2, lower: -2 },
  { date: "2024-06", spread: 1.8, upper: 2, lower: -2 },
  { date: "2024-07", spread: 0.5, upper: 2, lower: -2 },
  { date: "2024-08", spread: -0.5, upper: 2, lower: -2 },
  { date: "2024-09", spread: -1.2, upper: 2, lower: -2 },
  { date: "2024-10", spread: -0.8, upper: 2, lower: -2 },
  { date: "2024-11", spread: 0.2, upper: 2, lower: -2 },
  { date: "2024-12", spread: 0.8, upper: 2, lower: -2 },
]

export function PairTradingPage() {
  const [selectedPair, setSelectedPair] = useState(defaultPairs[0])
  const [selectedCategory, setSelectedCategory] = useState("全部")

  // 从后端获取配对交易数据
  const { data: pairsData, isLoading: pairsLoading } = useQuery({
    queryKey: ["pair-trading", "pairs"],
    queryFn: async () => {
      try {
        return await api.pair.list()
      } catch {
        return { pairs: defaultPairs }
      }
    },
  })

  // 获取价差数据
  const { data: spreadResponse = { data: mockSpreadData }, isLoading: spreadLoading } = useQuery({
    queryKey: ["pair-trading", "spread", selectedPair?.stock1, selectedPair?.stock2],
    queryFn: () => api.pair.spread(selectedPair.stock1, selectedPair.stock2),
    enabled: !!selectedPair,
  })

  // 从响应中提取数据数组
  const spreadData = spreadResponse?.data || mockSpreadData

  // 转换后端数据或使用模拟数据
  let pairs = defaultPairs

  if (pairsData?.pairs && pairsData.pairs.length > 0) {
    pairs = pairsData.pairs
  }

  // 按分类筛选
  const filteredPairs = selectedCategory === "全部"
    ? pairs
    : pairs.filter((p: any) => p.category === selectedCategory)

  const categories = ["全部", ...Array.from(new Set(pairs.map((p: any) => p.category)))]

  const getZScoreColor = (zScore: number) => {
    if (zScore > 2) return "text-down"
    if (zScore < -2) return "text-up"
    return "text-foreground"
  }

  const getSignalVariant = (signal: string) => {
    if (signal === "做多价差") return "default"
    if (signal === "做空价差") return "destructive"
    return "outline"
  }

  const getCointegrationBadge = (pValue: number) => {
    if (pValue < 0.01) return <Badge variant="default">强协整</Badge>
    if (pValue < 0.05) return <Badge className="bg-blue-600">协整</Badge>
    return <Badge variant="outline">弱协整</Badge>
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Link2 className="h-8 w-8 text-indigo-600" />
          配对交易
        </h1>
        <p className="text-muted-foreground">统计套利策略 - 协整关系与价差分析</p>
      </div>

      {/* 统计概览 */}
      <div className="grid gap-4 md:grid-cols-5">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">有效配对</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{pairs.length}</div>
            <p className="text-xs text-muted-foreground">协整关系稳定</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">平均相关性</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {(pairs.reduce((sum: number, p: any) => sum + p.correlation, 0) / pairs.length).toFixed(2)}
            </div>
            <p className="text-xs text-muted-foreground">价格相关系数</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">开仓机会</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-up">
              {pairs.filter((p: any) => p.status === "开仓机会").length}
            </div>
            <p className="text-xs text-muted-foreground">|Z-Score| &gt; 2</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">胜率</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">68.5%</div>
            <p className="text-xs text-muted-foreground">历史回测</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">强协整对</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {pairs.filter((p: any) => p.pValue < 0.01).length}
            </div>
            <p className="text-xs text-muted-foreground">p &lt; 0.01</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* 配对列表 */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <CardTitle>配对列表</CardTitle>
                  <CardDescription>基于协整关系的配对组合</CardDescription>
                </div>
                {/* 分类筛选 */}
                <div className="flex flex-wrap gap-2">
                  {categories.map((cat) => (
                    <Badge
                      key={cat}
                      variant={selectedCategory === cat ? "default" : "outline"}
                      className="cursor-pointer"
                      onClick={() => setSelectedCategory(cat)}
                    >
                      {cat}
                    </Badge>
                  ))}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {pairsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>配对组合</TableHead>
                      <TableHead>分类</TableHead>
                      <TableHead className="text-right">相关性</TableHead>
                      <TableHead className="text-right">协整检验</TableHead>
                      <TableHead className="text-right">Z-Score</TableHead>
                      <TableHead>信号</TableHead>
                      <TableHead>状态</TableHead>
                      <TableHead className="text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredPairs.map((pair: any) => (
                      <TableRow
                        key={pair.pair}
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => setSelectedPair(pair)}
                      >
                        <TableCell>
                          <div className="space-y-0.5">
                            <div className="font-medium">{pair.pair}</div>
                            <div className="text-xs text-muted-foreground">
                              {pair.stock1} / {pair.stock2}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{pair.category}</Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          {pair.correlation.toFixed(2)}
                        </TableCell>
                        <TableCell className="text-right">
                          {getCointegrationBadge(pair.pValue)}
                        </TableCell>
                        <TableCell className={`text-right font-medium ${getZScoreColor(pair.zScore)}`}>
                          {pair.zScore.toFixed(2)}
                        </TableCell>
                        <TableCell>
                          <Badge variant={getSignalVariant(pair.signal) as any}>
                            {pair.signal}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={pair.status === "开仓机会" ? "default" : "outline"}
                          >
                            {pair.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <a href={`/quote?stock=${pair.stock1}`} className="text-sm text-primary hover:underline">
                            详情
                          </a>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>

        {/* 配对详情 */}
        <div className="space-y-0.5">
          <Card>
            <CardHeader>
              <CardTitle>配对详情</CardTitle>
              <CardDescription>{selectedPair.pair}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-0.5">
                <p className="text-sm text-muted-foreground">股票 A</p>
                <p className="font-medium">{selectedPair.stock1}</p>
              </div>
              <div className="space-y-0.5">
                <p className="text-sm text-muted-foreground">股票 B</p>
                <p className="font-medium">{selectedPair.stock2}</p>
              </div>
              <div className="pt-4 border-t space-y-3">
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">相关性</span>
                  <span className="font-medium">{selectedPair.correlation.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">协整 p-value</span>
                  <span className="font-medium">{selectedPair.pValue.toFixed(3)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Z-Score</span>
                  <span className={`font-medium ${getZScoreColor(selectedPair.zScore)}`}>
                    {selectedPair.zScore.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">当前信号</span>
                  <Badge variant={getSignalVariant(selectedPair.signal) as any}>
                    {selectedPair.signal}
                  </Badge>
                </div>
              </div>

              {/* 操作建议 */}
              <div className="pt-4 border-t">
                <p className="text-sm font-medium mb-2 flex items-center gap-2">
                  <Activity className="h-4 w-4" />
                  操作建议
                </p>
                <div className="p-3 bg-muted rounded-lg text-sm">
                  {selectedPair.signal === "做多价差" && (
                    <p>
                      <span className="text-up font-medium">建议做多价差:</span>
                      买入 {selectedPair.stock1.split(" ")[0]}，做空 {selectedPair.stock2.split(" ")[0]}
                    </p>
                  )}
                  {selectedPair.signal === "做空价差" && (
                    <p>
                      <span className="text-down font-medium">建议做空价差:</span>
                      做空 {selectedPair.stock1.split(" ")[0]}，买入 {selectedPair.stock2.split(" ")[0]}
                    </p>
                  )}
                  {selectedPair.signal === "中性" && (
                    <p className="text-muted-foreground">
                      当前价差处于正常范围，建议等待更好时机
                    </p>
                  )}
                </div>
              </div>

              <a href="/backtest" className="block w-full">
                <Button className="w-full" variant="outline">
                  查看历史回测
                </Button>
              </a>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* 价差走势 */}
      <Card>
        <CardHeader>
          <CardTitle>价差走势</CardTitle>
          <CardDescription>
            {selectedPair.pair} - Z-Score 变化
          </CardDescription>
        </CardHeader>
        <CardContent>
          {spreadLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <LineChartComponent
              data={spreadData}
              lines={[
                { dataKey: "spread", name: "价差", color: "var(--color-primary)" },
                { dataKey: "upper", name: "上界 (+2σ)", color: "var(--color-down)" },
                { dataKey: "lower", name: "下界 (-2σ)", color: "var(--color-up)" },
              ]}
              xKey="date"
              height={300}
            />
          )}
        </CardContent>
      </Card>

      {/* 策略说明 */}
      <InstructionsPanel
        title="配对交易策略说明"
        description="统计套利策略 - 协整关系与价差分析"
        icon="info"
        defaultExpanded={false}
        instructions={commonInstructions.pairTrading}
      />
    </div>
  )
}
