// ETF筛选页面 - 全量 ETF 筛选分析
import { useState } from "react"
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
import { Target, Search, Filter, Loader2, Download } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { Heatmap } from "@/components/charts/heatmap"
import { BarChart } from "@/components/charts/bar-chart"
import { InstructionsPanel } from "@/components/features/instructions-panel"

// 模拟 ETF 数据
const mockEtfs = [
  { code: "512480", name: "半导体 ETF", category: "科技", pe: 35.2, size: 128.5, change: 5.2, volume: 12.3, sharpe: 1.25, calmar: 0.85, aboveMA20: 0.85, excessReturn: 8.5 },
  { code: "515790", name: "光伏 ETF", category: "新能源", pe: 28.5, size: 95.2, change: 1.2, volume: 8.5, sharpe: 0.95, calmar: 0.65, aboveMA20: 0.55, excessReturn: 2.1 },
  { code: "516390", name: "新能源车 ETF", category: "新能源", pe: 42.8, size: 156.8, change: 3.8, volume: 15.2, sharpe: 1.15, calmar: 0.75, aboveMA20: 0.78, excessReturn: 6.8 },
  { code: "512660", name: "军工 ETF", category: "国防", pe: 45.2, size: 85.3, change: 2.5, volume: 6.8, sharpe: 1.05, calmar: 0.70, aboveMA20: 0.65, excessReturn: 4.2 },
  { code: "512010", name: "医药 ETF", category: "医药", pe: 32.5, size: 198.5, change: -0.5, volume: 18.5, sharpe: 0.65, calmar: 0.45, aboveMA20: 0.45, excessReturn: -1.5 },
  { code: "159928", name: "消费 ETF", category: "消费", pe: 28.5, size: 235.6, change: -1.2, volume: 22.3, sharpe: 0.55, calmar: 0.35, aboveMA20: 0.35, excessReturn: -3.2 },
  { code: "516310", name: "金融 ETF", category: "金融", pe: 6.5, size: 156.2, change: -2.1, volume: 10.5, sharpe: 0.45, calmar: 0.30, aboveMA20: 0.25, excessReturn: -4.5 },
  { code: "512200", name: "地产 ETF", category: "地产", pe: 8.2, size: 45.8, change: -3.5, volume: 3.2, sharpe: -0.15, calmar: -0.10, aboveMA20: 0.15, excessReturn: -8.5 },
  { code: "512690", name: "白酒 ETF", category: "消费", pe: 32.8, size: 125.5, change: 0.8, volume: 9.5, sharpe: 0.75, calmar: 0.50, aboveMA20: 0.52, excessReturn: 0.5 },
  { code: "515030", name: "新能车 ETF", category: "新能源", pe: 38.5, size: 112.3, change: 2.8, volume: 11.2, sharpe: 1.05, calmar: 0.68, aboveMA20: 0.70, excessReturn: 5.2 },
  { code: "512400", name: "有色金属 ETF", category: "资源", pe: 22.5, size: 68.5, change: 1.5, volume: 5.8, sharpe: 0.85, calmar: 0.55, aboveMA20: 0.58, excessReturn: 2.8 },
  { code: "516160", name: "新能源 ETF", category: "新能源", pe: 35.8, size: 88.2, change: 2.2, volume: 7.5, sharpe: 0.95, calmar: 0.60, aboveMA20: 0.62, excessReturn: 3.5 },
]

const categories = ["全部", "科技", "新能源", "医药", "消费", "金融", "国防", "地产", "资源"]

const sortOptions = [
  { value: "change-desc", label: "涨跌幅（高→低）" },
  { value: "change-asc", label: "涨跌幅（低→高）" },
  { value: "size-desc", label: "规模（大→小）" },
  { value: "size-asc", label: "规模（小→大）" },
  { value: "volume-desc", label: "成交额（高→低）" },
  { value: "sharpe-desc", label: "夏普（高→低）" },
  { value: "pe-asc", label: "市盈率（低→高）" },
]

export function EtfScreenerPage() {
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedCategory, setSelectedCategory] = useState("全部")
  const [sortBy, setSortBy] = useState("change-desc")
  const [filters, setFilters] = useState({ minPe: "", maxPe: "", minSize: "" })
  const [dataSource, setDataSource] = useState<"core" | "all">("core")

  // 从后端获取ETF信号数据
  const { data: etfResponse, isLoading } = useQuery({
    queryKey: ["etf", "screener", dataSource],
    queryFn: () => api.etf.all(),
  })

  // 转换后端数据或使用模拟数据
  let etfData = mockEtfs

  if (etfResponse?.etfs && etfResponse.etfs.length > 0) {
    etfData = etfResponse.etfs.map((e: any) => ({
      code: e.code,
      name: e.name || e.code,
      category: e.category || "其他",
      pe: e.pe || 30,
      size: e.size || 100,
      change: e.change_pct || 0,
      volume: e.volume || 10,
      sharpe: e.sharpe || 0.8,
      calmar: e.calmar || 0.5,
      aboveMA20: e.above_ma20 || 0.5,
      excessReturn: e.excess_return || 0,
    }))
  }

  // 筛选和排序
  let filteredEtfs = etfData.filter((etf) => {
    const matchSearch =
      etf.name.includes(searchQuery) || etf.code.includes(searchQuery)
    const matchCategory =
      selectedCategory === "全部" || etf.category === selectedCategory

    let matchFilters = true
    if (filters.minPe) matchFilters = matchFilters && etf.pe >= parseFloat(filters.minPe)
    if (filters.maxPe) matchFilters = matchFilters && etf.pe <= parseFloat(filters.maxPe)
    if (filters.minSize) matchFilters = matchFilters && etf.size >= parseFloat(filters.minSize)

    return matchSearch && matchCategory && matchFilters
  })

  // 排序
  filteredEtfs = [...filteredEtfs].sort((a, b) => {
    const [field, order] = sortBy.split("-")
    const multiplier = order === "desc" ? -1 : 1

    if (field === "change") return (a.change - b.change) * multiplier
    if (field === "size") return (a.size - b.size) * multiplier
    if (field === "volume") return (a.volume - b.volume) * multiplier
    if (field === "pe") return (a.pe - b.pe) * multiplier
    if (field === "sharpe") return ((a.sharpe || 0) - (b.sharpe || 0)) * multiplier
    return 0
  })

  const stats = {
    total: filteredEtfs.length,
    avgPe: (filteredEtfs.reduce((sum, e) => sum + e.pe, 0) / filteredEtfs.length || 0).toFixed(1),
    avgSharpe: (filteredEtfs.reduce((sum, e) => sum + (e.sharpe || 0), 0) / filteredEtfs.length || 0).toFixed(2),
    totalSize: (filteredEtfs.reduce((sum, e) => sum + e.size, 0)).toFixed(0),
    upCount: filteredEtfs.filter((e) => e.change > 0).length,
    aboveMA20: (filteredEtfs.filter((e) => (e.aboveMA20 || 0) > 0.5).length),
  }

  // 准备 TOP 10 评分柱状图数据
  const top10Data = filteredEtfs.slice(0, 10).map((etf) => ({
    name: etf.name,
    评分: etf.sharpe ? Math.round(etf.sharpe * 20 + 50) : 60,
  }))

  // 准备热力图数据
  const heatmapData: Array<{ row: string; col: string; value: number; label?: string }> = []
  categories.slice(1).forEach((cat) => {
    const catEtfs = filteredEtfs.filter((e) => e.category === cat)
    const avgChange = catEtfs.reduce((sum, e) => sum + e.change, 0) / (catEtfs.length || 1)
    heatmapData.push({ row: cat, col: "涨跌幅", value: avgChange, label: `${avgChange.toFixed(1)}%` })
  })

  // 导出 CSV
  const handleExportCSV = () => {
    const csv = [
      ["代码", "名称", "分类", "市盈率", "规模(亿)", "涨跌幅", "成交额(亿)", "夏普比率"],
      ...filteredEtfs.map((e) => [
        e.code,
        e.name,
        e.category,
        e.pe.toFixed(1),
        e.size.toFixed(1),
        e.change.toFixed(2),
        e.volume.toFixed(1),
        (e.sharpe || 0).toFixed(2),
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
              占比 {((stats.upCount / stats.total) * 100).toFixed(0)}%
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
              占比 {((stats.aboveMA20 / stats.total) * 100).toFixed(0)}%
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
            onClick={() => setDataSource("core")}
          >
            核心50只
          </Badge>
          <Badge
            variant={dataSource === "all" ? "default" : "outline"}
            className="cursor-pointer"
            onClick={() => setDataSource("all")}
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
          rowLabels={categories.slice(1)}
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
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            {/* 分类筛选 */}
            <Select value={selectedCategory} onValueChange={setSelectedCategory}>
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
            <Select value={sortBy} onValueChange={setSortBy}>
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
              onChange={(e) => setFilters({ ...filters, minPe: e.target.value })}
            />

            {/* 规模筛选 */}
            <Input
              type="number"
              placeholder="最小规模(亿)"
              value={filters.minSize}
              onChange={(e) => setFilters({ ...filters, minSize: e.target.value })}
            />
          </div>

          <div className="flex justify-between mt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSearchQuery("")
                setSelectedCategory("全部")
                setFilters({ minPe: "", maxPe: "", minSize: "" })
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
                  <TableCell className="text-right">{etf.pe.toFixed(1)}</TableCell>
                  <TableCell className="text-right">{etf.size.toFixed(1)}</TableCell>
                  <TableCell className={`text-right ${etf.change >= 0 ? "text-up" : "text-down"}`}>
                    {etf.change >= 0 ? "+" : ""}{etf.change}%
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge variant={(etf.sharpe || 0) > 1 ? "default" : "outline"}>
                      {(etf.sharpe || 0).toFixed(2)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge variant={(etf.aboveMA20 || 0) > 0.5 ? "default" : "outline"}>
                  {((etf.aboveMA20 || 0) * 100).toFixed(0)}%
                    </Badge>
                  </TableCell>
                  <TableCell className={`text-right ${(etf.excessReturn || 0) >= 0 ? "text-up" : "text-down"}`}>
                    {(etf.excessReturn || 0) >= 0 ? "+" : ""}{(etf.excessReturn || 0).toFixed(1)}%
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
              const avgChange = catEtfs.reduce((sum, e) => sum + e.change, 0) / (catEtfs.length || 1)
              const avgSharpe = catEtfs.reduce((sum, e) => sum + (e.sharpe || 0), 0) / (catEtfs.length || 1)
              return (
                <Card key={cat}>
                  <CardContent className="pt-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium">{cat}</span>
                      <Badge variant="outline">{catEtfs.length}</Badge>
                    </div>
                    <div className={`text-sm ${avgChange >= 0 ? "text-up" : "text-down"}`}>
                      平均涨跌: {avgChange >= 0 ? "+" : ""}{avgChange.toFixed(1)}%
                    </div>
                    <div className="text-xs text-muted-foreground">
                      夏普: {avgSharpe.toFixed(2)}
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
