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
import { Link2, Loader2, Activity, AlertCircle } from "lucide-react"
import { LineChartComponent } from "@/components/charts/line-chart"
import { InstructionsPanel, commonInstructions } from "@/components/features/instructions-panel"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"

export function PairTradingPage() {
  const [selectedPair, setSelectedPair] = useState<any>(null)
  const [selectedCategory, setSelectedCategory] = useState("全部")

  // 从后端获取配对交易数据
  const { data: pairsData, isLoading: pairsLoading } = useQuery({
    queryKey: ["pair-trading", "pairs"],
    queryFn: () => api.pair.list(),
  })

  // 获取价差数据
  const { data: spreadResponse, isLoading: spreadLoading } = useQuery({
    queryKey: ["pair-trading", "spread", selectedPair?.stock1, selectedPair?.stock2],
    queryFn: () => api.pair.spread(selectedPair.stock1, selectedPair.stock2),
    enabled: !!selectedPair,
  })

  // 从响应中提取数据数组
  const spreadData = spreadResponse?.data || []
  const pairWarning = pairsData?.pairs?.find((p: any) => p.warning)?.warning
  const spreadWarning = spreadResponse?.warning

  // 转换后端数据
  let pairs: any[] = []

  if (pairsData?.pairs && pairsData.pairs.length > 0) {
    pairs = pairsData.pairs
  }

  // 按分类筛选
  const filteredPairs = selectedCategory === "全部"
    ? pairs
    : pairs.filter((p: any) => p.category === selectedCategory)

  const categories = ["全部", ...Array.from(new Set(pairs.map((p: any) => p.category)))]
  const availablePairs = pairs.filter((p: any) => p.data_status !== "unavailable")
  const avgCorrelation = availablePairs.length > 0
    ? (availablePairs.reduce((sum: number, p: any) => sum + (p.correlation ?? 0), 0) / availablePairs.length).toFixed(2)
    : "--"

  const formatNumber = (value: number | null | undefined, digits = 2) =>
    typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "--"

  const getZScoreColor = (zScore: number | null | undefined) => {
    if (typeof zScore !== "number") return "text-muted-foreground"
    if (zScore > 2) return "text-down"
    if (zScore < -2) return "text-up"
    return "text-foreground"
  }

  const getSignalVariant = (signal: string) => {
    if (signal === "做多价差") return "default"
    if (signal === "做空价差") return "destructive"
    return "outline"
  }

  const getCointegrationBadge = (pValue: number | null | undefined) => {
    if (typeof pValue !== "number") return <Badge variant="outline">无可靠数据</Badge>
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

      {(pairWarning || spreadWarning) && (
        <Card className="border-yellow-500/50 bg-yellow-500/10">
          <CardContent className="flex items-start gap-2 pt-4 text-sm text-yellow-700 dark:text-yellow-300">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{spreadWarning || pairWarning}</span>
          </CardContent>
        </Card>
      )}

      {/* 统计概览 */}
      <div className="grid gap-4 md:grid-cols-5">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">有效配对</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{availablePairs.length}</div>
            <p className="text-xs text-muted-foreground">有可靠指标</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">平均相关性</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {avgCorrelation}
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
            <div className="text-2xl font-bold">--</div>
            <p className="text-xs text-muted-foreground">基于API数据</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">强协整对</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {availablePairs.filter((p: any) => typeof p.pValue === "number" && p.pValue < 0.01).length}
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
                          {formatNumber(pair.correlation)}
                        </TableCell>
                        <TableCell className="text-right">
                          {getCointegrationBadge(pair.pValue)}
                        </TableCell>
                        <TableCell className={`text-right font-medium ${getZScoreColor(pair.zScore)}`}>
                          {formatNumber(pair.zScore)}
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
              <CardDescription>{selectedPair?.pair || "请从左侧列表选择配对"}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {!selectedPair ? (
                <div className="text-center py-8 text-muted-foreground">
                  点击左侧配对行查看详情
                </div>
              ) : (
              <>
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
                  <span className="font-medium">{formatNumber(selectedPair.correlation)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">协整 p-value</span>
                  <span className="font-medium">{formatNumber(selectedPair.pValue, 3)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Z-Score</span>
                  <span className={`font-medium ${getZScoreColor(selectedPair.zScore)}`}>
                    {formatNumber(selectedPair.zScore)}
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
                  {selectedPair.status === "不可用" && (
                    <p className="text-muted-foreground">
                      当前配对缺少可靠行情或价差数据，暂不生成交易建议。
                    </p>
                  )}
                </div>
              </div>

              <a href="/backtest" className="block w-full">
                <Button className="w-full" variant="outline">
                  查看历史回测
                </Button>
              </a>
              </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* 价差走势 */}
      <Card>
        <CardHeader>
          <CardTitle>价差走势</CardTitle>
          <CardDescription>
            {selectedPair?.pair || "价差"} - Z-Score 变化
          </CardDescription>
        </CardHeader>
        <CardContent>
          {spreadLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : (
            spreadData.length > 0 ? (
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
            ) : (
              <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
                暂无可靠价差数据
              </div>
            )
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
