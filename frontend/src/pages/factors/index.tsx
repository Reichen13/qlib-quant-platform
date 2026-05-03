// 因子分析页面 - Alpha158 因子 IC 分析
import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Microscope, Loader2, BarChart3, RefreshCw } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { BarChart } from "@/components/charts/bar-chart"
import { Histogram } from "@/components/charts/histogram"

// 预测周期选项
const predictPeriods = [
  { value: "1", label: "1 日" },
  { value: "5", label: "5 日" },
  { value: "10", label: "10 日" },
  { value: "20", label: "20 日" },
]

const dateRanges = [
  { value: "2026ytd", label: "2026 年初至今", start: "2026-01-01", end: "2026-04-30" },
  { value: "2025h2", label: "2025 下半年", start: "2025-07-01", end: "2025-12-31" },
  { value: "2025", label: "2025 全年", start: "2025-01-01", end: "2025-12-31" },
  { value: "2024h2", label: "2024 下半年", start: "2024-07-01", end: "2024-12-31" },
  { value: "2024", label: "2024 全年", start: "2024-01-01", end: "2024-12-31" },
  { value: "custom", label: "自定义", start: "", end: "" },
]

const factorCategories = ["全部", "技术指标", "量价", "财务", "风险"]

interface FactorItem {
  name: string
  ic: number
  rankIC: number
  type: string
  category: string
}

export function FactorAnalysisPage() {
  const [selectedCategory, setSelectedCategory] = useState("全部")
  const [sortBy, setSortBy] = useState<"ic" | "rankIC">("ic")
  const [predictPeriod, setPredictPeriod] = useState("5")
  const [dateRange, setDateRange] = useState("2026ytd")
  const [startDate, setStartDate] = useState("2026-01-01")
  const [endDate, setEndDate] = useState("2026-04-30")

  const { data: analyzeData, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["factors", "analyze", predictPeriod, startDate, endDate],
    queryFn: () => api.factors.analyze({
      start_date: startDate,
      end_date: endDate,
      predict_period: parseInt(predictPeriod),
      top_k: 158,
    }),
    enabled: true,
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
  })

  const handleDateRangeChange = (value: string) => {
    setDateRange(value)
    const range = dateRanges.find((item) => item.value === value)
    if (range && range.value !== "custom") {
      setStartDate(range.start)
      setEndDate(range.end)
    }
  }

  // 转换后端数据
  let factors: FactorItem[] = []

  if (analyzeData?.factors && analyzeData.factors.length > 0) {
    factors = analyzeData.factors.map((f: any) => ({
      name: f.factor.replace("$", ""),
      ic: f.ic,
      rankIC: f.rank_ic || f.ic,
      type: f.ic > 0 ? "动量" : "反转",
      category: "技术指标",
    }))
  }

  // 筛选和排序
  const filteredFactors = factors
    .filter((f) => selectedCategory === "全部" || f.category === selectedCategory)
    .sort((a, b) => Math.abs(b[sortBy]) - Math.abs(a[sortBy]))

  const avgIC = factors.length > 0 ? factors.reduce((sum, f) => sum + Math.abs(f.ic), 0) / factors.length : 0
  const maxIC = factors.length > 0 ? Math.max(...factors.map((f) => Math.abs(f.ic))) : 0
  const positiveCount = factors.filter((f) => f.ic > 0).length
  const negativeCount = factors.filter((f) => f.ic < 0).length

  // 准备柱状图数据
  const barChartData = filteredFactors.slice(0, 15).map((f) => ({
    name: f.name,
    IC: f.ic,
    "Rank IC": f.rankIC,
  }))

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Microscope className="h-8 w-8 text-purple-600" />
          因子分析
        </h1>
        <p className="text-muted-foreground">Alpha158 因子 IC 分析</p>
      </div>

      {/* 预测周期选择 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">分析参数</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-5">
            <div className="space-y-2">
              <Label>预测周期</Label>
              <Select value={predictPeriod} onValueChange={setPredictPeriod}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {predictPeriods.map((p) => (
                    <SelectItem key={p.value} value={p.value}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>数据周期</Label>
              <Select value={dateRange} onValueChange={handleDateRangeChange}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {dateRanges.map((range) => (
                    <SelectItem key={range.value} value={range.value}>
                      {range.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>开始日期</Label>
              <Input
                type="date"
                value={startDate}
                onChange={(event) => {
                  setDateRange("custom")
                  setStartDate(event.target.value)
                }}
              />
            </div>

            <div className="space-y-2">
              <Label>结束日期</Label>
              <Input
                type="date"
                value={endDate}
                onChange={(event) => {
                  setDateRange("custom")
                  setEndDate(event.target.value)
                }}
              />
            </div>

            <div className="space-y-2">
              <Label>&nbsp;</Label>
              <Button onClick={() => refetch()} disabled={isLoading} className="w-full">
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    分析中
                  </>
                ) : (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    运行分析
                  </>
                )}
              </Button>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Badge variant="outline">
              数据范围: {startDate} ~ {endDate}
            </Badge>
            <Badge variant="secondary">因子总数: {factors.length}</Badge>
          </div>
        </CardContent>
      </Card>

      {/* 加载中提示 */}
      {isFetching && (
        <Card className="border-yellow-600/50 bg-yellow-600/5">
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <Loader2 className="h-5 w-5 animate-spin text-yellow-600" />
              <div className="space-y-0.5">
                <p className="font-medium">Alpha158 因子分析中...</p>
                <p className="text-sm text-muted-foreground">
                  正在计算 158 个因子的 IC 值，首次分析需要 1-3 分钟，请耐心等待
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 错误提示 */}
      {error && !isFetching && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="py-6 text-center space-y-2">
            <p className="text-lg font-medium text-destructive">因子分析失败</p>
            <p className="text-sm text-muted-foreground">
              {String(error).includes("超时") ? "请求超时，请尝试缩短日期范围（如 3 个月）" : String(error)}
            </p>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              重新分析
            </Button>
          </CardContent>
        </Card>
      )}

      {/* 无数据提示 */}
      {!isFetching && !error && factors.length === 0 && (
        <Card>
          <CardContent className="py-8 text-center">
            <p className="text-lg font-medium">暂无因子分析结果</p>
            <p className="text-sm text-muted-foreground mt-1">
              请选择日期范围后点击"运行分析"按钮，或等待自动分析完成
            </p>
          </CardContent>
        </Card>
      )}

      {/* 统计概览 */}
      <div className="grid gap-4 md:grid-cols-5">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">因子总数</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{factors.length}</div>
            <p className="text-xs text-muted-foreground">Alpha158 体系</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">平均 IC</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-up">
              {avgIC.toFixed(3)}
            </div>
            <p className="text-xs text-muted-foreground">绝对值平均</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">最大 IC</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-up">
              {maxIC.toFixed(3)}
            </div>
            <p className="text-xs text-muted-foreground">
              {factors.find((f) => Math.abs(f.ic) === maxIC)?.name}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">有效因子</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {factors.filter((f) => Math.abs(f.ic) > 0.02).length}
            </div>
            <p className="text-xs text-muted-foreground">|IC| &gt; 0.02</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">正向/负向</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {positiveCount}/{negativeCount}
            </div>
            <p className="text-xs text-muted-foreground">正负因子比</p>
          </CardContent>
        </Card>
      </div>

      {/* 图表区域 */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* IC 柱状图 */}
        <BarChart
          data={barChartData}
          bars={[
            { dataKey: "IC", name: "IC", color: "var(--color-primary)" },
            { dataKey: "Rank IC", name: "Rank IC", color: "var(--color-up)" },
          ]}
          xKey="name"
          height={350}
          title="因子 IC 排行"
          description={`Top ${Math.min(15, filteredFactors.length)} 因子 IC 值对比`}
        />

        {/* IC 分布直方图 */}
        <Histogram
          data={factors.length > 0 ? (() => {
            const bins = [
              { bin: "<-0.06", min: -Infinity, max: -0.06, count: 0 },
              { bin: "-0.06~-0.04", min: -0.06, max: -0.04, count: 0 },
              { bin: "-0.04~-0.02", min: -0.04, max: -0.02, count: 0 },
              { bin: "-0.02~0", min: -0.02, max: 0, count: 0 },
              { bin: "0~0.02", min: 0, max: 0.02, count: 0 },
              { bin: "0.02~0.04", min: 0.02, max: 0.04, count: 0 },
              { bin: "0.04~0.06", min: 0.04, max: 0.06, count: 0 },
              { bin: ">0.06", min: 0.06, max: Infinity, count: 0 },
            ]
            for (const f of factors) {
              for (const b of bins) {
                if (f.ic >= b.min && f.ic < b.max) { b.count++; break }
              }
            }
            return bins.map(b => ({ bin: b.bin, count: b.count }))
          })() : []}
          title="因子 IC 分布"
          description="所有因子 IC 值的分布情况"
          height={350}
          mean={avgIC}
          std={Math.sqrt(factors.reduce((sum, f) => sum + Math.pow(f.ic - avgIC, 2), 0) / factors.length)}
        />
      </div>

      {/* 因子分析内容 */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* 因子列表 */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <CardTitle>因子 IC 分析</CardTitle>
                  <CardDescription>
                    因子与收益率的相关系数分析
                  </CardDescription>
                </div>
                <Tabs value={sortBy} onValueChange={(v) => setSortBy(v as any)}>
                  <TabsList>
                    <TabsTrigger value="ic">IC</TabsTrigger>
                    <TabsTrigger value="rankIC">Rank IC</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
            </CardHeader>
            <CardContent>
              {/* 分类筛选 */}
              <div className="flex flex-wrap gap-2 mb-4">
                {factorCategories.map((cat) => (
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

              {isLoading && !analyzeData ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>因子名称</TableHead>
                      <TableHead>类型</TableHead>
                      <TableHead>分类</TableHead>
                      <TableHead className="text-right">IC</TableHead>
                      <TableHead className="text-right">Rank IC</TableHead>
                      <TableHead className="text-right">ICIR</TableHead>
                      <TableHead className="text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredFactors.map((factor) => (
                      <TableRow key={factor.name}>
                        <TableCell className="font-medium">
                          {factor.name}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{factor.type}</Badge>
                        </TableCell>
                        <TableCell>{factor.category}</TableCell>
                        <TableCell className="text-right">
                          <span
                            className={
                              factor.ic >= 0 ? "text-up" : "text-down"
                            }
                          >
                            {factor.ic >= 0 ? "+" : ""}
                            {factor.ic.toFixed(3)}
                          </span>
                        </TableCell>
                        <TableCell className="text-right">
                          <span
                            className={
                              factor.rankIC >= 0 ? "text-up" : "text-down"
                            }
                          >
                            {factor.rankIC >= 0 ? "+" : ""}
                            {factor.rankIC.toFixed(3)}
                          </span>
                        </TableCell>
                        <TableCell className="text-right text-muted-foreground">
                          {(factor.ic / (0.02 + Math.abs(factor.ic))).toFixed(2)}
                        </TableCell>
                        <TableCell className="text-right">
                          <button className="text-sm text-muted-foreground hover:text-foreground">
                            分析
                          </button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>

        {/* 因子分布 */}
        <div className="space-y-0.5">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5" />
                因子分布
              </CardTitle>
              <CardDescription>IC 值分布统计</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="space-y-0.5">
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="text-muted-foreground">正向因子</span>
                    <span className="font-medium">
                      {positiveCount}
                    </span>
                  </div>
                  <div className="h-3 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-up"
                      style={{
                        width: `${
                          (positiveCount / factors.length) * 100
                        }%`,
                      }}
                    />
                  </div>
                </div>

                <div className="space-y-0.5">
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="text-muted-foreground">负向因子</span>
                    <span className="font-medium">
                      {negativeCount}
                    </span>
                  </div>
                  <div className="h-3 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-down"
                      style={{
                        width: `${
                          (negativeCount / factors.length) * 100
                        }%`,
                      }}
                    />
                  </div>
                </div>

                <div className="pt-4 border-t">
                  <h4 className="text-sm font-medium mb-3">Top 5 因子</h4>
                  <div className="space-y-2">
                    {factors
                      .sort((a, b) => Math.abs(b.ic) - Math.abs(a.ic))
                      .slice(0, 5)
                      .map((f) => (
                        <div
                          key={f.name}
                          className="flex items-center justify-between text-sm"
                        >
                          <span className="text-muted-foreground">
                            {f.name}
                          </span>
                          <span
                            className={
                              f.ic >= 0 ? "text-up font-medium" : "text-down font-medium"
                            }
                          >
                            {f.ic >= 0 ? "+" : ""}
                            {f.ic.toFixed(3)}
                          </span>
                        </div>
                      ))}
                  </div>
                </div>

                <div className="pt-4 border-t">
                  <h4 className="text-sm font-medium mb-3">因子类型分布</h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">技术指标</span>
                      <span>
                        {factors.filter((f) => f.category === "技术指标").length}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">量价</span>
                      <span>
                        {factors.filter((f) => f.category === "量价").length}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">财务</span>
                      <span>
                        {factors.filter((f) => f.category === "财务").length}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">风险</span>
                      <span>
                        {factors.filter((f) => f.category === "风险").length}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
