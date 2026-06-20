// ETF筛选页面 - 全量 ETF 筛选分析
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Target, Search, Filter, Loader2, Download, AlertCircle } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useAppStore } from "@/stores/app-store"
import { Heatmap } from "@/components/charts/heatmap"
import { BarChart } from "@/components/charts/bar-chart"
import { InstructionsPanel } from "@/components/features/instructions-panel"

const categories = ["全部", "宽基", "科技", "新能源", "医药", "消费", "金融", "国防", "资源", "其他"]

const sortOptions = [
  { value: "change-desc", label: "涨跌幅（高→低）" },
  { value: "change-asc", label: "涨跌幅（低→高）" },
  { value: "size-desc", label: "规模（大→小）" },
  { value: "size-asc", label: "规模（小→大）" },
  { value: "volume-desc", label: "成交额（高→低）" },
  { value: "sharpe-desc", label: "夏普（高→低）" },
]

export function EtfScreenerPage() {
  const etfScreenerParams = useAppStore((s) => s.etfScreenerParams)
  const setEtfScreenerParams = useAppStore((s) => s.setEtfScreenerParams)
  const searchQuery = etfScreenerParams.searchQuery
  const selectedCategory = etfScreenerParams.selectedCategory
  const sortBy = etfScreenerParams.sortBy
  const filters = etfScreenerParams.filters
  const dataSource = etfScreenerParams.dataSource

  // 从后端获取ETF信号数据
  const { data: etfResponse, isLoading } = useQuery({
    queryKey: ["etf", "screener", dataSource],
    queryFn: () => api.etf.all(),
  })

  // 转换后端真实数据；缺失指标保持为空，不再填默认值
  let etfData: any[] = []

  if (etfResponse?.etfs && etfResponse.etfs.length > 0) {
    etfData = etfResponse.etfs.map((e: any) => ({
      code: e.code,
      name: e.name || e.code,
      category: e.type || e.category || "其他",
      pe: e.pe ?? null,
      size: e.size ?? null,
      change: e.change_pct ?? null,
      volume: e.amount ?? null,
      sharpe: e.sharpe ?? null,
      calmar: e.calmar ?? null,
      aboveMA20: e.above_ma20 ?? null,
      excessReturn: e.excess_return ?? null,
      warning: e.warning,
      dataStatus: e.data_status || "ok",
    }))
  }

  const formatNumber = (value: number | null | undefined, digits = 1) =>
    typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "--"

  const numericValue = (value: number | null | undefined, fallback: number) =>
    typeof value === "number" && Number.isFinite(value) ? value : fallback
  const finiteNumber = (value: number | null | undefined): value is number =>
    typeof value === "number" && Number.isFinite(value)

  // 筛选和排序
  let filteredEtfs = etfData.filter((etf) => {
    const matchSearch =
      etf.name.includes(searchQuery) || etf.code.includes(searchQuery)
    const matchCategory =
      selectedCategory === "全部" || etf.category === selectedCategory

    let matchFilters = true
    if (filters.minPe) matchFilters = matchFilters && typeof etf.pe === "number" && etf.pe >= parseFloat(filters.minPe)
    if (filters.maxPe) matchFilters = matchFilters && typeof etf.pe === "number" && etf.pe <= parseFloat(filters.maxPe)
    if (filters.minSize) matchFilters = matchFilters && typeof etf.size === "number" && etf.size >= parseFloat(filters.minSize)

    return matchSearch && matchCategory && matchFilters
  })

  // 排序
  filteredEtfs = [...filteredEtfs].sort((a, b) => {
    const [field, order] = sortBy.split("-")
    const multiplier = order === "desc" ? -1 : 1

    if (field === "change") return (numericValue(a.change, -Infinity) - numericValue(b.change, -Infinity)) * multiplier
    if (field === "size") return (numericValue(a.size, -Infinity) - numericValue(b.size, -Infinity)) * multiplier
    if (field === "volume") return (numericValue(a.volume, -Infinity) - numericValue(b.volume, -Infinity)) * multiplier
    if (field === "sharpe") return (numericValue(a.sharpe, -Infinity) - numericValue(b.sharpe, -Infinity)) * multiplier
    return 0
  })

  const sharpeValues = filteredEtfs.map((e) => e.sharpe).filter((v) => typeof v === "number")
  const sizeValues = filteredEtfs.map((e) => e.size).filter((v) => typeof v === "number")

  const stats = {
    total: filteredEtfs.length,
    avgSharpe: sharpeValues.length ? (sharpeValues.reduce((sum, v) => sum + v, 0) / sharpeValues.length).toFixed(2) : "--",
    totalSize: sizeValues.length ? sizeValues.reduce((sum, v) => sum + v, 0).toFixed(0) : "--",
    upCount: filteredEtfs.filter((e) => typeof e.change === "number" && e.change > 0).length,
    aboveMA20: (filteredEtfs.filter((e) => e.aboveMA20 === 1).length),
  }

  // 准备 TOP 10 评分柱状图数据
  const rankedBySharpe = filteredEtfs.filter((etf) => finiteNumber(etf.sharpe))
  const top10Data = rankedBySharpe.slice(0, 10).map((etf) => ({
    name: etf.name,
    评分: Math.max(0, Math.min(100, Math.round(etf.sharpe * 20 + 50))),
  }))

  // 准备热力图数据
  const heatmapData: Array<{ row: string; col: string; value: number; label?: string }> = []
  categories.slice(1).forEach((cat) => {
    const catEtfs = filteredEtfs.filter((e) => e.category === cat)
    const changes = catEtfs.map((e) => e.change).filter((v) => typeof v === "number")
    if (changes.length > 0) {
      const avgChange = changes.reduce((sum, v) => sum + v, 0) / changes.length
      heatmapData.push({ row: cat, col: "涨跌幅", value: avgChange, label: `${avgChange.toFixed(1)}%` })
    }
  })
  const heatmapRows = [...new Set(heatmapData.map((item) => item.row))]

  // 导出 CSV
  const handleExportCSV = () => {
    const csv = [
      ["代码", "名称", "分类", "市盈率", "规模(亿)", "涨跌幅", "成交额(亿)", "夏普比率"],
      ...filteredEtfs.map((e) => [
        e.code,
        e.name,
        e.category,
        formatNumber(e.pe, 1),
        formatNumber(e.size, 1),
        formatNumber(e.change, 2),
        formatNumber(e.volume, 1),
        formatNumber(e.sharpe, 2),
      ]),
    ]
      .map((row) => row.join(","))
      .join("\n")

    const blob = new Blob([csv], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `etf_screener_${new Date().toISOString().split("T")[0]}.csv`
    a.click()
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Target className="h-8 w-8 text-rose-600" />
          ETF 筛选
        </h1>
        <p className="text-muted-foreground">全量 ETF 筛选分析 - {dataSource === "core" ? "核心50只" : "全量300+只"}</p>
      </div>

      {/* 统计概览 */}
      {etfResponse?.warning && (
        <Card className="border-yellow-500/50 bg-yellow-500/10">
          <CardContent className="flex items-start gap-2 pt-4 text-sm text-yellow-700 dark:text-yellow-300">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{etfResponse.warning}</span>
          </CardContent>
        </Card>
      )}

      <Card className="border-blue-500/40 bg-blue-500/5">
        <CardContent className="flex items-start gap-2 pt-4 text-sm text-muted-foreground">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
          <span>本页只展示后端可获取或可由行情计算的真实指标；PE、基金规模等暂未取得可靠来源时显示为 --。</span>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-5">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">筛选结果</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total}</div>
            <p className="text-xs text-muted-foreground">
              {dataSource === "core" ? "核心50" : "全量300+"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">平均夏普</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.avgSharpe}</div>
            <p className="text-xs text-muted-foreground">风险调整收益</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">总规模</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalSize}</div>
            <p className="text-xs text-muted-foreground">亿元</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">上涨数量</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-up">{stats.upCount}</div>
            <p className="text-xs text-muted-foreground">
              占比 {stats.total ? ((stats.upCount / stats.total) * 100).toFixed(0) : "--"}%
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">站上MA20</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-up">{stats.aboveMA20}</div>
            <p className="text-xs text-muted-foreground">
              占比 {stats.total ? ((stats.aboveMA20 / stats.total) * 100).toFixed(0) : "--"}%
            </p>
          </CardContent>
        </Card>
      </div>

      {/* 数据源切换 */}
      <div className="flex items-center gap-4">
        <div className="flex gap-2">
          <Badge
            variant={dataSource === "core" ? "default" : "outline"}
            className="cursor-pointer"
            onClick={() => setEtfScreenerParams({ dataSource: "core" })}
          >
            核心50只
          </Badge>
          <Badge
            variant={dataSource === "all" ? "default" : "outline"}
            className="cursor-pointer"
            onClick={() => setEtfScreenerParams({ dataSource: "all" })}
          >
            全量300+
          </Badge>
        </div>
      </div>

      {/* 图表区域 */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* TOP 10 评分 */}
        <BarChart
          data={top10Data}
          bars={[{ dataKey: "评分", name: "综合评分", color: "var(--color-primary)" }]}
          xKey="name"
          height={280}
          title="TOP 10 评分"
          description="综合夏普比率排序"
        />

        {/* 分类动量热力图 */}
        <Heatmap
          data={heatmapData}
          rowLabels={heatmapRows}
          colLabels={["涨跌幅"]}
          title="分类动量热力图"
          description="各分类涨跌幅分布"
          colorScale="green-red"
        />
      </div>

      {/* 筛选条件 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-5 w-5" />
            筛选条件
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-5">
            {/* 搜索框 */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="搜索名称/代码"
                className="pl-9"
                value={searchQuery}
                onChange={(e) => setEtfScreenerParams({ searchQuery: e.target.value })}
              />
            </div>

            {/* 分类筛选 */}
            <Select value={selectedCategory} onValueChange={(value) => setEtfScreenerParams({ selectedCategory: value })}>
              <SelectTrigger>
                <SelectValue placeholder="选择分类" />
              </SelectTrigger>
              <SelectContent>
                {categories.map((cat) => (
                  <SelectItem key={cat} value={cat}>
                    {cat}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* 排序方式 */}
            <Select value={sortBy} onValueChange={(value) => setEtfScreenerParams({ sortBy: value })}>
              <SelectTrigger>
                <SelectValue placeholder="排序方式" />
              </SelectTrigger>
              <SelectContent>
                {sortOptions.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* PE 最小值 */}
            <Input
              type="number"
              placeholder="最小 PE"
              value={filters.minPe}
              onChange={(e) => setEtfScreenerParams({ filters: { minPe: e.target.value } })}
            />

            {/* 规模筛选 */}
            <Input
              type="number"
              placeholder="最小规模(亿)"
              value={filters.minSize}
              onChange={(e) => setEtfScreenerParams({ filters: { minSize: e.target.value } })}
            />
          </div>

          <div className="flex justify-between mt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setEtfScreenerParams({
                  searchQuery: "",
                  selectedCategory: "全部",
                  filters: { minPe: "", maxPe: "", minSize: "" },
                })
              }}
            >
              重置筛选
            </Button>
            <Button size="sm" onClick={handleExportCSV}>
              <Download className="mr-2 h-4 w-4" />
              导出 CSV
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ETF 列表 */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <CardTitle>ETF 列表</CardTitle>
              <CardDescription>找到 {stats.total} 只符合条件的 ETF</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>代码</TableHead>
                  <TableHead>名称</TableHead>
                  <TableHead>分类</TableHead>
                  <TableHead className="text-right">市盈率</TableHead>
                  <TableHead className="text-right">规模(亿)</TableHead>
                  <TableHead className="text-right">涨跌幅</TableHead>
                  <TableHead className="text-right">夏普</TableHead>
                  <TableHead className="text-right">站上MA20</TableHead>
                  <TableHead className="text-right">超额收益</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
            <TableBody>
              {filteredEtfs.map((etf) => (
                <TableRow key={etf.code}>
                  <TableCell className="font-medium">{etf.code}</TableCell>
                  <TableCell>{etf.name}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{etf.category}</Badge>
                  </TableCell>
                  <TableCell className="text-right">{formatNumber(etf.pe, 1)}</TableCell>
                  <TableCell className="text-right">{formatNumber(etf.size, 1)}</TableCell>
                  <TableCell className={`text-right ${(etf.change ?? 0) >= 0 ? "text-up" : "text-down"}`}>
                    {typeof etf.change === "number" ? `${etf.change >= 0 ? "+" : ""}${etf.change.toFixed(2)}%` : "--"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge variant={(etf.sharpe || 0) > 1 ? "default" : "outline"}>
                      {formatNumber(etf.sharpe, 2)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge variant={etf.aboveMA20 === 1 ? "default" : "outline"}>
                      {typeof etf.aboveMA20 === "number" ? `${(etf.aboveMA20 * 100).toFixed(0)}%` : "--"}
                    </Badge>
                  </TableCell>
                  <TableCell className={`text-right ${(etf.excessReturn ?? 0) >= 0 ? "text-up" : "text-down"}`}>
                    {typeof etf.excessReturn === "number" ? `${etf.excessReturn >= 0 ? "+" : ""}${etf.excessReturn.toFixed(1)}%` : "--"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm">
                      详情
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          )}
        </CardContent>
      </Card>

      {/* 分类概览 */}
      <Card>
        <CardHeader>
          <CardTitle>分类概览</CardTitle>
          <CardDescription>各分类 ETF 数量与平均表现</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-4">
            {categories.slice(1).map((cat) => {
              const catEtfs = filteredEtfs.filter((e) => e.category === cat)
              const catChanges = catEtfs.map((e) => e.change).filter((v) => typeof v === "number")
              const catSharpes = catEtfs.map((e) => e.sharpe).filter((v) => typeof v === "number")
              const avgChange = catChanges.length ? catChanges.reduce((sum, v) => sum + v, 0) / catChanges.length : null
              const avgSharpe = catSharpes.length ? catSharpes.reduce((sum, v) => sum + v, 0) / catSharpes.length : null
              return (
                <Card key={cat}>
                  <CardContent className="pt-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium">{cat}</span>
                      <Badge variant="outline">{catEtfs.length}</Badge>
                    </div>
                    <div className={`text-sm ${avgChange == null ? "text-muted-foreground" : avgChange >= 0 ? "text-up" : "text-down"}`}>
                      平均涨跌: {avgChange == null ? "--" : `${avgChange >= 0 ? "+" : ""}${avgChange.toFixed(1)}%`}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      夏普: {avgSharpe == null ? "--" : avgSharpe.toFixed(2)}
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* 使用说明 */}
      <InstructionsPanel
        title="ETF 筛选说明"
        description="全市场 ETF 多维度筛选指标解读"
        icon="info"
        defaultExpanded={false}
        variant="compact"
        instructions={[
          {
            title: "夏普比率",
            description: "衡量风险调整后收益，夏普 > 1 为优秀，> 2 为卓越。计算公式：年化收益率 / 年化波动率",
          },
          {
            title: "Calmar 比率",
            description: "收益回撤比，数值越大越好。计算公式：年化收益率 / 最大回撤绝对值",
          },
          {
            title: "站上 MA20 比例",
            description: "当前价格高于 20 日均线的交易日占比，反映趋势强度",
          },
          {
            title: "超额收益",
            description: "相对于沪深300基准的超额收益率，正值表示跑赢基准",
          },
          {
            title: "动量热力图",
            description: "颜色深浅表示近期涨跌幅，红色为上涨，绿色为下跌",
          },
        ]}
      />
    </div>
  )
}
