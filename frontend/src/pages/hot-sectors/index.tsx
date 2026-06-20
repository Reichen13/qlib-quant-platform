// 主题热点页面 - 行业板块涨跌幅排行
import { Fragment, useState } from "react"
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Flame, TrendingUp, TrendingDown, RefreshCw, Loader2, ChevronDown, ChevronRight, Star, BarChart3 } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { BarChart } from "@/components/charts/bar-chart"
import { InstructionsPanel } from "@/components/features/instructions-panel"

interface SectorItem {
  name: string
  change: number
  volume: number | null
  stocks: number
  factorScore?: number
  advice?: string
  leader?: string
}

export function HotSectorsPage() {
  const [period, setPeriod] = useState("10d")
  const [expandedSector, setExpandedSector] = useState<string | null>(null)
  const [isUpdating, setIsUpdating] = useState(false)

  const { data: sectorData, isLoading, isError, refetch } = useQuery({
    queryKey: ["sectors-performance", period],
    queryFn: () => api.sectors.performance(parseInt(period.replace('d', ''))),
  })

  // 获取板块成分股
  const { data: sectorStocks } = useQuery({
    queryKey: ["sectors-stocks", expandedSector],
    queryFn: () => api.sectors.stocks(expandedSector!),
    enabled: !!expandedSector,
  })

  // 转换后端真实数据；后端没有返回的指标保持为空
  let sectors: SectorItem[] = []
  let apiError = false

  if (sectorData?.sectors && sectorData.sectors.length > 0) {
    sectors = sectorData.sectors.map((s: any) => ({
      name: s.industry,
      change: s.change_pct,
      volume: null,
      stocks: s.stock_count,
      factorScore: undefined,
      advice: s.change_pct > 2 ? "强势" : s.change_pct > 0 ? "关注" : s.change_pct > -2 ? "观望" : "规避",
    }))
  } else if (isError) {
    apiError = true
  }

  const sortedSectors = [...sectors].sort((a, b) => b.change - a.change)

  // 准备柱状图数据 - 使用真实数据
  const barChartData = sectors.map((sector) => ({
    name: sector.name,
    涨跌幅: sector.change,
  }))

  const handleUpdate = async () => {
    setIsUpdating(true)
    await refetch()
    setTimeout(() => setIsUpdating(false), 1000)
  }

  const toggleSector = (sectorName: string) => {
    setExpandedSector(expandedSector === sectorName ? null : sectorName)
  }

  const getAdviceBadge = (advice: string) => {
    switch (advice) {
      case "强势":
        return <Badge variant="default">强势</Badge>
      case "关注":
        return <Badge className="bg-blue-600">关注</Badge>
      case "中性":
        return <Badge variant="outline">中性</Badge>
      case "观望":
        return <Badge className="bg-yellow-600">观望</Badge>
      case "规避":
        return <Badge variant="destructive">规避</Badge>
      default:
        return <Badge variant="outline">{advice}</Badge>
    }
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Flame className="h-8 w-8 text-orange-600" />
          主题热点
        </h1>
        <p className="text-muted-foreground">行业板块涨跌幅排行</p>
      </div>

      {/* 控制栏 */}
      <div className="flex items-center justify-between">
        <Tabs value={period} onValueChange={(v) => setPeriod(v as any)}>
          <TabsList>
            <TabsTrigger value="1d">1日</TabsTrigger>
            <TabsTrigger value="5d">5日</TabsTrigger>
            <TabsTrigger value="10d">10日</TabsTrigger>
            <TabsTrigger value="20d">20日</TabsTrigger>
          </TabsList>
        </Tabs>

        <Button onClick={handleUpdate} disabled={isUpdating}>
          {isUpdating ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              更新中...
            </>
          ) : (
            <>
              <RefreshCw className="mr-2 h-4 w-4" />
              更新数据
            </>
          )}
        </Button>
      </div>

      {/* 统计概览 */}
      <div className="grid gap-4 md:grid-cols-5">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">上涨板块</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-up">
              {sectors.filter((s) => s.change > 0).length}
            </div>
            <p className="text-xs text-muted-foreground">共 {sectors.length} 个板块</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">领涨板块</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-up">
              {sortedSectors[0]?.name || "--"}
            </div>
            <p className="text-xs text-up">
              +{sortedSectors[0]?.change.toFixed(2)}%
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">领跌板块</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-down">
              {sortedSectors[sortedSectors.length - 1]?.name || "--"}
            </div>
            <p className="text-xs text-down">
              {sortedSectors[sortedSectors.length - 1]?.change.toFixed(2)}%
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">总成交额</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              --
            </div>
            <p className="text-xs text-muted-foreground">暂无可靠成交额</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">市场热度</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {sectors.filter((s) => Math.abs(s.change) > 2).length > 5 ? "高" : "中等"}
            </div>
            <p className="text-xs text-muted-foreground">
              {sectors.filter((s) => Math.abs(s.change) > 2).length} 个活跃板块
            </p>
          </CardContent>
        </Card>
      </div>

      {/* 板块涨跌幅柱状图 */}
      <BarChart
        data={barChartData}
        bars={[
          {
            dataKey: "涨跌幅",
            name: "涨跌幅",
            color: "var(--color-primary)",
          },
        ]}
        xKey="name"
        height={280}
        title="板块涨跌幅排行"
        description={`近 ${period.replace("d", "")} 日行业板块表现`}
      />

      {/* 板块详情表格 */}
      <Card>
        <CardHeader>
          <CardTitle>板块详情</CardTitle>
          <CardDescription>
            点击展开查看板块成分股
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading && !sectorData ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">排名</TableHead>
                  <TableHead>板块名称</TableHead>
                  <TableHead className="text-right">涨跌幅</TableHead>
                  <TableHead className="text-right">成交额(亿)</TableHead>
                  <TableHead className="text-right">成分股数</TableHead>
                  <TableHead className="text-right">因子评分</TableHead>
                  <TableHead>操作建议</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedSectors.map((sector, index) => (
                  <Fragment key={sector.name}>
                    <TableRow
                      key={sector.name}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => toggleSector(sector.name)}
                    >
                      <TableCell className="font-medium">
                        {index + 1}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {index < 3 && sector.change > 0 && (
                            <Star className="h-4 w-4 text-yellow-500" />
                          )}
                          <span className="font-medium">{sector.name}</span>
                          {expandedSector === sector.name && (
                            <span className="text-xs text-muted-foreground">(点击收起)</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className={`text-right font-medium ${
                        sector.change >= 0 ? "text-up" : "text-down"
                      }`}>
                        {sector.change >= 0 ? "+" : ""}{sector.change.toFixed(2)}%
                      </TableCell>
                      <TableCell className="text-right">
                        {typeof sector.volume === "number" ? sector.volume.toFixed(1) : "--"}
                      </TableCell>
                      <TableCell className="text-right">{sector.stocks}</TableCell>
                      <TableCell className="text-right">
                        {sector.factorScore !== undefined ? (
                          <Badge variant={sector.factorScore >= 80 ? "default" : "outline"}>
                            {sector.factorScore}
                          </Badge>
                        ) : (
                          "--"
                        )}
                      </TableCell>
                      <TableCell>
                        {sector.advice ? getAdviceBadge(sector.advice) : "--"}
                      </TableCell>
                      <TableCell className="text-right">
                        {expandedSector === sector.name ? (
                          <ChevronDown className="h-4 w-4 ml-auto" />
                        ) : (
                          <ChevronRight className="h-4 w-4 ml-auto" />
                        )}
                      </TableCell>
                    </TableRow>

                    {/* 成分股展开行 */}
                    {expandedSector === sector.name && (
                      <TableRow>
                        <TableCell colSpan={8} className="bg-muted/30">
                          <div className="py-4">
                            <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
                              <BarChart3 className="h-4 w-4" />
                              {sector.name} 成分股
                            </h4>
                            <div className="grid gap-2">
                              {sectorStocks?.stocks && sectorStocks.stocks.length > 0 ? (
                                sectorStocks.stocks.slice(0, 10).map((stock: any) => (
                                  <div
                                    key={stock.code}
                                    className="flex items-center justify-between p-3 bg-background rounded-lg"
                                  >
                                    <div className="space-y-0.5">
                                      <span className="font-medium">{stock.name}</span>
                                      <span className="text-xs text-muted-foreground ml-2">
                                        {stock.code}
                                      </span>
                                    </div>
                                  </div>
                                ))
                              ) : (
                                <div className="text-center py-4 text-muted-foreground text-sm">
                                  暂无成分股数据
                                </div>
                              )}
                            </div>
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* 市场情绪分析 */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-up" />
              上涨板块分析
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {sortedSectors
                .filter((s) => s.change > 0)
                .slice(0, 5)
                .map((sector) => (
                  <div key={sector.name} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span>{sector.name}</span>
                      <span className="text-up font-medium">
                        +{sector.change.toFixed(2)}%
                      </span>
                    </div>
                    <div className="h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-up rounded-full"
                        style={{
                          width: `${(sector.change / (sortedSectors[0]?.change || 1)) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingDown className="h-5 w-5 text-down" />
              下跌板块分析
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {sortedSectors
                .filter((s) => s.change < 0)
                .sort((a, b) => a.change - b.change)
                .slice(0, 5)
                .map((sector) => (
                  <div key={sector.name} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span>{sector.name}</span>
                      <span className="text-down font-medium">
                        {sector.change.toFixed(2)}%
                      </span>
                    </div>
                    <div className="h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-down rounded-full"
                        style={{
                          width: `${
                            (Math.abs(sector.change) /
                              Math.abs(sortedSectors[sortedSectors.length - 1]?.change || 1)) *
                            100
                          }%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 使用说明 */}
      <InstructionsPanel
        title="主题热点使用说明"
        description="行业板块涨跌幅排行与成分股分析"
        icon="info"
        defaultExpanded={false}
        instructions={[
          {
            title: "涨跌幅排行",
            description: "反映不同周期（1日/5日/10日/20日）内各行业板块的涨跌情况",
          },
          {
            title: "因子评分",
            description: "综合技术指标、资金流向等多维度计算得出，评分越高表示板块越强势",
          },
          {
            title: "操作建议",
            description: "基于板块强弱和因子评分给出参考建议：强势（买入）、关注（持有）、中性（观望）、规避（减仓）",
          },
          {
            title: "成分股分析",
            description: "点击板块名称可展开查看该板块的主要成分股及其表现",
          },
        ]}
      />

      {/* API 错误提示 */}
      {apiError && (
        <Card className="border-red-200 bg-red-50 dark:bg-red-950/20">
          <CardContent className="pt-4">
            <p className="text-sm text-red-800 dark:text-red-200">
              无法连接到后端 API，请检查服务是否正常运行
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
