// 因子分析页面 - Alpha158 因子 IC 分析
import { useState, useMemo } from "react"
import { useAppStore } from "@/stores/app-store"
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Microscope, Loader2, BarChart3, RefreshCw, X, Layers } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { BarChart } from "@/components/charts/bar-chart"
import { Histogram } from "@/components/charts/histogram"
import { LineChartComponent } from "@/components/charts/line-chart"

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

interface FactorItem {
  name: string
  ic: number
  rankIC: number
  icir: number
  type: string
  category: string
  skewness?: number | null
  kurtosis?: number | null
  tStatistic?: number | null
  pValue?: number | null
  informationRatio?: number | null
  icAutocorr?: number | null
  industryContribution?: Record<string, number> | null
}

export function FactorAnalysisPage() {
  const [selectedCategory, setSelectedCategory] = useState("全部")
  const [sortBy, setSortBy] = useState<"ic" | "rankIC">("ic")
  const factorParams = useAppStore((s) => s.factorParams)
  const setFactorParams = useAppStore((s) => s.setFactorParams)
  const predictPeriod = String(factorParams.predictPeriod)
  const startDate = factorParams.startDate
  const endDate = factorParams.endDate
  const neutralize = factorParams.neutralize || "none"

  const [selectedFactor, setSelectedFactor] = useState<string | null>(null)
  const [detailTab, setDetailTab] = useState<"ic_stability" | "factor_series" | "industry_contrib">("ic_stability")
  const [showDecay, setShowDecay] = useState(false)
  const [showCombination, setShowCombination] = useState(false)
  const [showAdvancedStats, setShowAdvancedStats] = useState(false)

  const { data: analyzeData, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["factors", "analyze", predictPeriod, startDate, endDate, neutralize],
    queryFn: () => api.factors.analyze({
      start_date: startDate,
      end_date: endDate,
      predict_period: parseInt(predictPeriod),
      top_k: 158,
      neutralize: neutralize === "industry" ? "industry" : undefined,
    }),
    enabled: true,
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
  })

  // 获取因子列表（用于动态分类）
  const { data: factorListData } = useQuery({
    queryKey: ["factors", "list"],
    queryFn: () => api.factors.list(),
    staleTime: Infinity,
    gcTime: Infinity,
  })

  // 动态分类
  const dynamicCategories = useMemo(() => {
    const cats = new Set<string>()
    if (factorListData?.factors) {
      for (const f of factorListData.factors) {
        const cat = f.category || "其他"
        if (cat) cats.add(cat)
      }
    }
    if (analyzeData?.factors) {
      for (const f of analyzeData.factors) {
        if (f.category) cats.add(f.category)
      }
    }
    return ["全部", ...Array.from(cats).sort()]
  }, [factorListData, analyzeData])

  // 单因子详情
  const { data: factorDetail, isLoading: detailLoading } = useQuery({
    queryKey: ["factors", "detail", selectedFactor, startDate, endDate, predictPeriod],
    queryFn: () => api.factors.detail(selectedFactor!, startDate, endDate, parseInt(predictPeriod)),
    enabled: !!selectedFactor,
  })

  // IC 衰减分析
  const { data: decayData, isLoading: decayLoading } = useQuery({
    queryKey: ["factors", "decay", predictPeriod, startDate, endDate],
    queryFn: () => api.factors.decay({
      start_date: startDate,
      end_date: endDate,
      predict_period: parseInt(predictPeriod),
      top_k: 10,
    }),
    enabled: showDecay && !!analyzeData && analyzeData.factors?.length > 0,
  })

  // 信号组合
  const { data: combineData, isLoading: combineLoading } = useQuery({
    queryKey: ["factors", "combine", predictPeriod, startDate, endDate],
    queryFn: () => api.factors.combine({
      start_date: startDate,
      end_date: endDate,
      predict_period: parseInt(predictPeriod),
      top_k: 10,
    }),
    enabled: showCombination && !!analyzeData,
  })

  const decayChartData = useMemo(() => {
    if (!decayData?.periods || !decayData?.decay_data) return []
    return decayData.periods.map((period: number, idx: number) => {
      const row: Record<string, string | number> = { period: `${period}日` }
      decayData.decay_data.slice(0, 6).forEach((d: any) => {
        row[d.factor] = d.ic_values[idx]
      })
      return row
    })
  }, [decayData])

  const handleDateRangeChange = (value: string) => {
    const range = dateRanges.find((item) => item.value === value)
    if (range && range.value !== "custom") {
      setFactorParams({ startDate: range.start, endDate: range.end })
    }
  }

  // 转换后端数据
  let factors: FactorItem[] = []

  if (analyzeData?.factors && analyzeData.factors.length > 0) {
    factors = analyzeData.factors.map((f: any) => ({
      name: f.factor.replace("$", ""),
      ic: f.ic,
      rankIC: f.rank_ic || f.ic,
      icir: f.icir || 0,
      type: f.ic > 0 ? "动量" : "反转",
      category: f.category || "未分类",
      skewness: f.skewness,
      kurtosis: f.kurtosis,
      tStatistic: f.t_statistic,
      pValue: f.p_value,
      informationRatio: f.information_ratio,
      icAutocorr: f.ic_autocorr,
      industryContribution: f.industry_contribution,
    }))
  }

  // 筛选和排序
  const filteredFactors = factors
    .filter((f) => selectedCategory === "全部" || f.category === selectedCategory)
    .sort((a, b) => Math.abs(b[sortBy]) - Math.abs(a[sortBy]))

  const selectedFactorObj = filteredFactors.find((f) => f.name === selectedFactor) || null

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
          <div className="grid gap-4 md:grid-cols-6">
            <div className="space-y-2">
              <Label>预测周期</Label>
              <Select value={predictPeriod} onValueChange={(v) => setFactorParams({ predictPeriod: Number(v) })}>
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
              <Select value={dateRanges.find(r => r.start === startDate && r.end === endDate)?.value || "custom"} onValueChange={handleDateRangeChange}>
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
              <Label>行业中性化</Label>
              <Select value={neutralize} onValueChange={(v) => setFactorParams({ neutralize: v })}>
                <SelectTrigger>
                  <SelectValue placeholder="无" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">无中性化</SelectItem>
                  <SelectItem value="industry">行业中性化 (OLS)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>开始日期</Label>
              <Input
                type="date"
                value={startDate}
                onChange={(event) => {
                  setFactorParams({ startDate: event.target.value })
                }}
              />
            </div>

            <div className="space-y-2">
              <Label>结束日期</Label>
              <Input
                type="date"
                value={endDate}
                onChange={(event) => {
                  setFactorParams({ endDate: event.target.value })
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
            {neutralize === "industry" && (
              <Badge variant="default" className="bg-purple-600">行业中性化</Badge>
            )}
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
                <div className="flex items-center gap-3">
                  <Button
                    variant={showAdvancedStats ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => setShowAdvancedStats(!showAdvancedStats)}
                  >
                    <BarChart3 className="mr-1 h-3 w-3" />
                    {showAdvancedStats ? "隐藏高级统计" : "高级统计"}
                  </Button>
                  <Tabs value={sortBy} onValueChange={(v) => setSortBy(v as any)}>
                    <TabsList>
                      <TabsTrigger value="ic">IC</TabsTrigger>
                      <TabsTrigger value="rankIC">Rank IC</TabsTrigger>
                    </TabsList>
                  </Tabs>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {/* 分类筛选 */}
              <div className="flex flex-wrap gap-2 mb-4">
                {dynamicCategories.map((cat) => (
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
                      {showAdvancedStats && (
                        <>
                          <TableHead className="text-right">t 值</TableHead>
                          <TableHead className="text-right">p 值</TableHead>
                          <TableHead className="text-right">IR</TableHead>
                          <TableHead className="text-right">IC 自相关</TableHead>
                        </>
                      )}
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
                          {factor.icir ? factor.icir.toFixed(2) : "-"}
                        </TableCell>
                        {showAdvancedStats && (
                          <>
                            <TableCell className="text-right">
                              <span className={factor.tStatistic != null ? (Math.abs(factor.tStatistic) >= 1.96 ? "text-up font-medium" : "text-muted-foreground") : "text-muted-foreground"}>
                                {factor.tStatistic != null ? factor.tStatistic.toFixed(2) : "-"}
                              </span>
                            </TableCell>
                            <TableCell className="text-right">
                              <span className={factor.pValue != null ? (factor.pValue < 0.05 ? "text-up font-medium" : "text-muted-foreground") : "text-muted-foreground"}>
                                {factor.pValue != null ? factor.pValue.toFixed(4) : "-"}
                              </span>
                            </TableCell>
                            <TableCell className="text-right text-muted-foreground">
                              {factor.informationRatio != null ? factor.informationRatio.toFixed(2) : "-"}
                            </TableCell>
                            <TableCell className="text-right text-muted-foreground">
                              {factor.icAutocorr != null ? factor.icAutocorr.toFixed(2) : "-"}
                            </TableCell>
                          </>
                        )}
                        <TableCell className="text-right">
                          <button
                            className="text-sm text-primary hover:underline"
                            onClick={() => { setSelectedFactor(factor.name); setDetailTab("ic_stability") }}
                          >
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
                    {dynamicCategories.slice(1).map((cat) => {
                      const count = factors.filter((f) => f.category === cat).length
                      if (count === 0) return null
                      return (
                        <div key={cat} className="flex justify-between">
                          <span className="text-muted-foreground">{cat}</span>
                          <span>{count}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* 因子详情面板 */}
      {selectedFactor && (
        <Card className="border-primary/50">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                因子详情: {selectedFactor}
                {factorDetail?.category && (
                  <Badge variant="outline" className="ml-2">{factorDetail.category}</Badge>
                )}
              </CardTitle>
              <Button variant="ghost" size="icon" onClick={() => setSelectedFactor(null)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            {factorDetail && (
              <CardDescription>
                Mean IC: {factorDetail.mean_ic} | Std IC: {factorDetail.std_ic} | ICIR: {factorDetail.icir}
              </CardDescription>
            )}
          </CardHeader>
          <CardContent>
            {detailLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : factorDetail ? (
              <Tabs value={detailTab} onValueChange={(v) => setDetailTab(v as any)}>
                <TabsList>
                  <TabsTrigger value="ic_stability">IC 稳定性</TabsTrigger>
                  <TabsTrigger value="factor_series">因子时序</TabsTrigger>
                  <TabsTrigger value="industry_contrib">行业贡献</TabsTrigger>
                </TabsList>
                <TabsContent value="ic_stability" className="mt-4">
                  <LineChartComponent
                    data={factorDetail.daily_ics?.map((d: any) => ({
                      date: d.date,
                      IC: d.ic,
                    })) || []}
                    lines={[{ dataKey: "IC", name: "每日 IC", color: "var(--color-primary)" }]}
                    xKey="date"
                    height={280}
                  />
                </TabsContent>
                <TabsContent value="factor_series" className="mt-4">
                  <LineChartComponent
                    data={factorDetail.factor_series?.map((d: any) => ({
                      date: d.date,
                      均值: d.value,
                    })) || []}
                    lines={[{ dataKey: "均值", name: "因子均值", color: "var(--color-up)" }]}
                    xKey="date"
                    height={280}
                  />
                </TabsContent>
                <TabsContent value="industry_contrib" className="mt-4">
                  {selectedFactorObj?.industryContribution && Object.keys(selectedFactorObj.industryContribution).length > 0 ? (
                    <BarChart
                      data={Object.entries(selectedFactorObj.industryContribution)
                        .sort((a, b) => a[1] - b[1])
                        .slice(-15)
                        .map(([ind, val]) => ({ name: ind, 贡献: val }))}
                      bars={[{ dataKey: "贡献", name: "行业贡献", color: "var(--color-primary)" }]}
                      xKey="name"
                      height={350}
                      title="行业加权 IC 贡献"
                      description="正值表示该行业内因子预测能力更强"
                    />
                  ) : (
                    <p className="text-center py-12 text-muted-foreground">
                      {neutralize ? "该因子暂无行业贡献数据" : "需先启用行业中性化后才能查看行业贡献"}
                    </p>
                  )}
                </TabsContent>
              </Tabs>
            ) : (
              <div className="text-center py-8 text-muted-foreground">暂无详情数据</div>
            )}
          </CardContent>
        </Card>
      )}

      {/* IC 衰减分析 */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <CardTitle>IC 衰减分析</CardTitle>
              <CardDescription>Top 因子在不同预测周期下的 IC 变化趋势</CardDescription>
            </div>
            <Button
              variant="outline"
              disabled={!analyzeData || analyzeData.factors?.length === 0}
              onClick={() => setShowDecay(!showDecay)}
            >
              {showDecay ? "刷新分析" : "运行衰减分析"}
            </Button>
          </div>
        </CardHeader>
        {showDecay && (
          <CardContent>
            {decayLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : decayData ? (
              <>
                <LineChartComponent
                  data={decayChartData}
                  lines={decayData.factors?.slice(0, 6).map((f: string) => ({
                    dataKey: f,
                    name: f,
                  })) || []}
                  xKey="period"
                  height={350}
                />
                <p className="text-xs text-muted-foreground mt-2">
                  X 轴为预测周期（1/3/5/10/20日），Y 轴为 IC 值。IC 衰减越快说明信号持续性越弱。
                </p>
              </>
            ) : (
              <div className="text-center py-8 text-muted-foreground">暂无衰减数据</div>
            )}
          </CardContent>
        )}
      </Card>

      {/* 信号组合 */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <CardTitle className="flex items-center gap-2">
                <Layers className="h-5 w-5" />
                信号组合评分
              </CardTitle>
              <CardDescription>IC 加权复合信号，识别最优选股</CardDescription>
            </div>
            <Button
              variant="outline"
              disabled={!analyzeData || analyzeData.factors?.length === 0}
              onClick={() => setShowCombination(!showCombination)}
            >
              {showCombination ? "刷新评分" : "构建复合信号"}
            </Button>
          </div>
        </CardHeader>
        {showCombination && (
          <CardContent>
            {combineLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : combineData ? (
              <div className="grid gap-6 md:grid-cols-2">
                <div>
                  <h4 className="text-sm font-medium mb-3">因子权重 (IC 加权)</h4>
                  <div className="space-y-2">
                    {combineData.factor_weights?.map((fw: any) => (
                      <div key={fw.factor} className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-muted-foreground truncate max-w-[160px]">{fw.factor}</span>
                          <span className="font-medium">{(fw.weight * 100).toFixed(1)}%</span>
                        </div>
                        <div className="h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary rounded-full"
                            style={{ width: `${fw.weight * 100}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <h4 className="text-sm font-medium mb-3">Top 选股 ({combineData.date})</h4>
                  <div className="space-y-2">
                    {combineData.top_stocks?.slice(0, 10).map((s: any, i: number) => (
                      <div key={s.code} className="flex items-center justify-between text-sm p-2 bg-muted/50 rounded">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="w-6 h-6 flex items-center justify-center p-0 text-xs">
                            {i + 1}
                          </Badge>
                          <span className="font-medium">{s.code}</span>
                        </div>
                        <Badge variant={s.score > 0 ? "default" : "outline"}>
                          {s.score.toFixed(2)}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">暂无组合数据</div>
            )}
          </CardContent>
        )}
      </Card>
    </div>
  )
}
