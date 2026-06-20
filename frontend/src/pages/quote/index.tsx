// 行情分析页面
import { useState, useMemo, useRef, useEffect, useCallback } from "react"
import { useSearchParams } from "react-router-dom"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
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
import { TrendingUp, Search, Loader2, Activity, BarChart3, Download } from "lucide-react"
import { CandlestickChart } from "@/components/charts/candlestick-chart"
import { InstructionsPanel, commonInstructions } from "@/components/features/instructions-panel"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useAppStore } from "@/stores/app-store"

// 热门股票列表（使用 Qlib 代码格式 SH/SZ + 数字）
const popularStocks = [
  { code: "SH600519", name: "贵州茅台" },
  { code: "SH600036", name: "招商银行" },
  { code: "SZ000001", name: "平安银行" },
  { code: "SZ000002", name: "万科A" },
  { code: "SZ000858", name: "五粮液" },
  { code: "SH601318", name: "中国平安" },
  { code: "SH600276", name: "恒瑞医药" },
  { code: "SZ000333", name: "美的集团" },
  { code: "SZ002594", name: "比亚迪" },
  { code: "SZ300750", name: "宁德时代" },
]

interface SearchResult {
  code: string
  name: string
  market: string
}

export function QuoteAnalysisPage() {
  const [searchParams] = useSearchParams()
  const quoteParams = useAppStore((s) => s.quoteParams)
  const setQuoteParams = useAppStore((s) => s.setQuoteParams)
  const selectedStock = quoteParams?.selectedStock || "SH600519"
  const timeframe = quoteParams?.timeframe || "daily"
  const showMA = quoteParams?.showMA ?? true
  const showBollinger = quoteParams?.showBollinger ?? true
  const showVolume = quoteParams?.showVolume ?? true
  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [showDropdown, setShowDropdown] = useState(false)
  const searchRef = useRef<HTMLDivElement>(null)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const urlCode = searchParams.get("stock") || searchParams.get("code")
    if (urlCode && urlCode.toUpperCase() !== selectedStock) {
      setQuoteParams({ selectedStock: urlCode.toUpperCase() })
    }
  }, [searchParams, selectedStock, setQuoteParams])

  // 点击外部关闭下拉
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  // 搜索防抖
  const handleSearchInput = useCallback((value: string) => {
    setSearchQuery(value)
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    if (!value.trim()) {
      setSearchResults([])
      setShowDropdown(false)
      return
    }
    debounceTimer.current = setTimeout(async () => {
      try {
        const base = import.meta.env.DEV ? "http://localhost:8000" : ""
        const res = await fetch(`${base}/api/stocks/search?q=${encodeURIComponent(value)}`)
        const data = await res.json()
        setSearchResults(data.results || [])
        setShowDropdown(true)
      } catch {
        setSearchResults([])
      }
    }, 300)
  }, [])

  const selectStock = (code: string) => {
    setQuoteParams({ selectedStock: code })
    setSearchQuery("")
    setShowDropdown(false)
  }
  // 获取股票行情
  const { data: quoteData, isLoading: quoteLoading } = useQuery({
    queryKey: ["quote", selectedStock, timeframe],
    queryFn: () => api.quote.getKline(selectedStock, timeframe),
    enabled: !!selectedStock,
    staleTime: 5 * 60 * 1000,
  })

  // 转换后端数据格式
  let chartData: any[] = []

  if (quoteData?.data && quoteData.data.length > 0) {
    chartData = quoteData.data.map((d: any) => ({
      time: new Date(d.date).getTime() / 1000,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
      volume: d.volume || 0,
    }))
  }

  const stockName = popularStocks.find((s) => s.code === selectedStock)?.name || selectedStock

  // 计算移动平均线
  const calculateMA = (data: typeof chartData, period: number) => {
    return data.map((_d, i) => {
      if (i < period - 1) return null
      const sum = data.slice(i - period + 1, i + 1).reduce((acc, val) => acc + val.close, 0)
      return sum / period
    })
  }

  // 计算布林带
  const calculateBollinger = (data: typeof chartData, period: number = 20, stdDev: number = 2) => {
    const upper: (number | null)[] = []
    const middle: (number | null)[] = []
    const lower: (number | null)[] = []

    for (let i = 0; i < data.length; i++) {
      if (i < period - 1) {
        upper.push(null)
        middle.push(null)
        lower.push(null)
      } else {
        const slice = data.slice(i - period + 1, i + 1)
        const sum = slice.reduce((acc, val) => acc + val.close, 0)
        const mean = sum / period
        const variance = slice.reduce((acc, val) => acc + Math.pow(val.close - mean, 2), 0) / period
        const std = Math.sqrt(variance)

        middle.push(mean)
        upper.push(mean + stdDev * std)
        lower.push(mean - stdDev * std)
      }
    }

    return { upper, middle, lower }
  }

  // 计算RSI
  const calculateRSI = (data: typeof chartData, period: number = 14) => {
    const rsi: (number | null)[] = []
    for (let i = 0; i < data.length; i++) {
      if (i < period) {
        rsi.push(null)
      } else {
        let gains = 0, losses = 0
        for (let j = i - period + 1; j <= i; j++) {
          const change = data[j].close - data[j - 1].close
          if (change > 0) gains += change
          else losses -= change
        }
        const avgGain = gains / period
        const avgLoss = losses / period
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss
        rsi.push(100 - 100 / (1 + rs))
      }
    }
    return rsi
  }

  // 计算MACD
  const calculateMACD = (data: typeof chartData) => {
    const ema12: number[] = []
    const ema26: number[] = []
    const macd: (number | null)[] = []
    const signal: (number | null)[] = []
    const histogram: (number | null)[] = []
    const multiplier12 = 2 / (12 + 1)
    const multiplier26 = 2 / (26 + 1)
    const multiplier9 = 2 / (9 + 1)

    for (let i = 0; i < data.length; i++) {
      if (i === 0) {
        ema12.push(data[i].close)
        ema26.push(data[i].close)
      } else {
        ema12.push((data[i].close - ema12[i - 1]) * multiplier12 + ema12[i - 1])
        ema26.push((data[i].close - ema26[i - 1]) * multiplier26 + ema26[i - 1])
      }
      macd.push(ema12[i] - ema26[i])
    }

    // 计算Signal线 (MACD的9日EMA)
    for (let i = 0; i < macd.length; i++) {
      if (i === 0) {
        signal.push(macd[i] ?? 0)
      } else {
        const prevSignal = signal[i - 1] ?? 0
        const currentMACD = macd[i] ?? 0
        signal.push((currentMACD - prevSignal) * multiplier9 + prevSignal)
      }
      histogram.push((macd[i] ?? 0) - (signal[i] ?? 0))
    }

    return { macd, signal, histogram }
  }

  // 技术指标数据
  const ma5 = useMemo(() => calculateMA(chartData, 5), [chartData])
  const ma10 = useMemo(() => calculateMA(chartData, 10), [chartData])
  const ma20 = useMemo(() => calculateMA(chartData, 20), [chartData])
  const ma60 = useMemo(() => calculateMA(chartData, 60), [chartData])
  const bollinger = useMemo(() => calculateBollinger(chartData, 20, 2), [chartData])
  const rsi = useMemo(() => calculateRSI(chartData, 14), [chartData])
  const macdData = useMemo(() => calculateMACD(chartData), [chartData])

  // 构建图表用的指标数据
  const chartMAData = useMemo(() =>
    chartData.map((d, i) => ({
      time: d.time,
      ma5: ma5[i],
      ma10: ma10[i],
      ma20: ma20[i],
      ma60: ma60[i],
    })),
    [chartData, ma5, ma10, ma20, ma60]
  )

  const chartBollingerData = useMemo(() =>
    chartData.map((d, i) => ({
      time: d.time,
      upper: bollinger.upper[i],
      middle: bollinger.middle[i],
      lower: bollinger.lower[i],
    })),
    [chartData, bollinger]
  )

  const chartVolumeData = useMemo(() =>
    chartData.map((d) => ({
      time: d.time,
      value: d.volume || 0,
      color: d.close >= d.open
        ? "rgba(38,166,154,0.4)"
        : "rgba(239,83,80,0.4)",
    })),
    [chartData]
  )

  // 当前技术指标值
  const currentPrice = chartData[chartData.length - 1]?.close
  const currentRSI = rsi[rsi.length - 1]
  const currentMACD = macdData.macd[macdData.macd.length - 1]
  const currentSignal = macdData.signal[macdData.signal.length - 1]
  const currentHistogram = macdData.histogram[macdData.histogram.length - 1]
  const currentMA5 = ma5[ma5.length - 1]
  const currentMA20 = ma20[ma20.length - 1]
  const currentBollingerUpper = bollinger.upper[bollinger.upper.length - 1]
  const currentBollingerLower = bollinger.lower[bollinger.lower.length - 1]
  const currentBollingerMiddle = bollinger.middle[bollinger.middle.length - 1]
  const recent20 = chartData.slice(-20)
  const high20 = recent20.length > 0 ? Math.max(...recent20.map((d) => d.high)) : null
  const low20 = recent20.length > 0 ? Math.min(...recent20.map((d) => d.low)) : null

  // 趋势判断
  const getTrend = () => {
    if (!currentMA5 || !currentMA20) return "未知"
    if (currentMA5 > currentMA20) return "上升"
    if (currentMA5 < currentMA20) return "下降"
    return "震荡"
  }

  // RSI信号
  const getRSISignal = () => {
    if (!currentRSI) return "未知"
    if (currentRSI > 70) return "超买"
    if (currentRSI < 30) return "超卖"
    return "中性"
  }

  // 布林带信号
  const getBollingerSignal = () => {
    if (!currentPrice || !currentBollingerUpper || !currentBollingerLower) return "未知"
    if (currentPrice > currentBollingerUpper) return "突破上轨"
    if (currentPrice < currentBollingerLower) return "跌破下轨"
    return "区间震荡"
  }

  // MACD信号
  const getMACDSignal = () => {
    if (currentHistogram === null) return "未知"
    const prevHistogram = macdData.histogram[macdData.histogram.length - 2] ?? 0
    if (currentHistogram > 0 && prevHistogram < 0) return "金叉买入"
    if (currentHistogram < 0 && prevHistogram > 0) return "死叉卖出"
    return currentHistogram > 0 ? "多头" : "空头"
  }

  // 导出数据
  const handleExport = () => {
    const csv = [
      ["日期", "开盘", "最高", "最低", "收盘", "成交量", "MA5", "MA20", "RSI", "MACD"],
      ...chartData.map((d, i) => [
        new Date(d.time * 1000).toISOString().split("T")[0],
        d.open.toFixed(2),
        d.high.toFixed(2),
        d.low.toFixed(2),
        d.close.toFixed(2),
        d.volume,
        ma5[i]?.toFixed(2) || "",
        ma20[i]?.toFixed(2) || "",
        rsi[i]?.toFixed(2) || "",
        macdData.macd[i]?.toFixed(4) || "",
      ]),
    ]
      .map((row) => row.join(","))
      .join("\n")

    const blob = new Blob([csv], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${selectedStock}_data.csv`
    a.click()
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <TrendingUp className="h-8 w-8 text-blue-600" />
          行情分析
        </h1>
        <p className="text-muted-foreground">K线图、技术指标分析</p>
      </div>

      {/* 搜索和选择 */}
      <Card>
        <CardHeader>
          <CardTitle>股票查询</CardTitle>
          <CardDescription>选择股票代码查看 K 线图</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* 搜索框 */}
          <div ref={searchRef} className="flex gap-2 relative">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="输入股票代码或名称，如 茅台 或 600519"
                className="pl-9"
                value={searchQuery}
                onChange={(e) => handleSearchInput(e.target.value)}
                onFocus={() => searchResults.length > 0 && setShowDropdown(true)}
              />
            </div>
            {showDropdown && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-card border rounded-lg shadow-lg z-50 max-h-64 overflow-y-auto">
                {searchResults.length > 0 ? (
                  searchResults.map((r) => (
                    <button
                      key={r.code}
                      className="w-full flex items-center justify-between px-4 py-2 hover:bg-accent text-left transition-colors"
                      onClick={() => selectStock(r.code)}
                    >
                      <span className="font-medium">{r.name}</span>
                      <span className="text-xs text-muted-foreground">{r.code}</span>
                    </button>
                  ))
                ) : (
                  <div className="px-4 py-3 text-sm text-muted-foreground">未找到匹配的股票</div>
                )}
              </div>
            )}
          </div>

          {/* 热门股票 */}
          <div className="space-y-0.5">
            <p className="text-sm text-muted-foreground mb-2">热门股票</p>
            <div className="flex flex-wrap gap-2">
              {popularStocks.map((stock) => (
                <Badge
                  key={stock.code}
                  variant={selectedStock === stock.code ? "default" : "outline"}
                  className="cursor-pointer hover:bg-accent"
                  onClick={() => setQuoteParams({ selectedStock: stock.code })}
                >
                  {stock.name}
                </Badge>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* K线图和技术指标 */}
      {selectedStock && (
        <>
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div className="space-y-0.5">
                  <CardTitle>{stockName}</CardTitle>
                  <CardDescription>代码: {selectedStock}</CardDescription>
                </div>
                <div className="flex items-center gap-4">
                  <Tabs value={timeframe} onValueChange={(v) => setQuoteParams({ timeframe: v as "daily" | "weekly" | "monthly" })}>
                    <TabsList>
                      <TabsTrigger value="daily">日K</TabsTrigger>
                      <TabsTrigger value="weekly">周K</TabsTrigger>
                      <TabsTrigger value="monthly">月K</TabsTrigger>
                    </TabsList>
                  </Tabs>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={showMA ? "default" : "outline"}
                      className="cursor-pointer"
                      onClick={() => setQuoteParams({ showMA: !showMA })}
                    >
                      MA
                    </Badge>
                    <Badge
                      variant={showBollinger ? "default" : "outline"}
                      className="cursor-pointer"
                      onClick={() => setQuoteParams({ showBollinger: !showBollinger })}
                    >
                      BOLL
                    </Badge>
                    <Badge
                      variant={showVolume ? "default" : "outline"}
                      className="cursor-pointer"
                      onClick={() => setQuoteParams({ showVolume: !showVolume })}
                    >
                      成交量
                    </Badge>
                  </div>
                  <Button variant="outline" size="sm" onClick={handleExport}>
                    <Download className="mr-2 h-4 w-4" />
                    导出
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {quoteLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <CandlestickChart
                  data={chartData}
                  maData={chartMAData}
                  bollingerData={chartBollingerData}
                  volumeData={chartVolumeData}
                  showMA={showMA}
                  showBollinger={showBollinger}
                  showVolume={showVolume}
                  height={400}
                />
              )}
            </CardContent>
          </Card>

          {/* 技术指标卡片 */}
          <div className="grid gap-4 md:grid-cols-3">
            {/* 移动平均线 */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Activity className="h-4 w-4" />
                  移动平均线
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">MA5</span>
                    <span className="font-medium text-foreground">
                      {currentMA5?.toFixed(2) || "--"}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">MA10</span>
                    <span className="font-medium text-blue-400">
                      {ma10[ma10.length - 1]?.toFixed(2) || "--"}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">MA20</span>
                    <span className="font-medium text-purple-400">
                      {currentMA20?.toFixed(2) || "--"}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">MA60</span>
                    <span className="font-medium text-yellow-400">
                      {ma60[ma60.length - 1]?.toFixed(2) || "--"}
                    </span>
                  </div>
                  <div className="pt-2 border-t">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-muted-foreground">趋势</span>
                      <Badge variant={
                        getTrend() === "上升" ? "default" :
                        getTrend() === "下降" ? "destructive" : "outline"
                      }>
                        {getTrend()}
                      </Badge>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* 布林带 */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <BarChart3 className="h-4 w-4" />
                  布林带 (20, 2)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">上轨</span>
                    <span className="font-medium text-red-400">
                      {currentBollingerUpper?.toFixed(2) || "--"}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">中轨</span>
                    <span className="font-medium text-yellow-400">
                      {currentBollingerMiddle?.toFixed(2) || "--"}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">下轨</span>
                    <span className="font-medium text-green-400">
                      {currentBollingerLower?.toFixed(2) || "--"}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">当前价</span>
                    <span className="font-medium">
                      {currentPrice?.toFixed(2) || "--"}
                    </span>
                  </div>
                  <div className="pt-2 border-t">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-muted-foreground">位置</span>
                      <Badge variant={getBollingerSignal() === "突破上轨" ? "destructive" : "outline"}>
                        {getBollingerSignal()}
                      </Badge>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* RSI指标 */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Activity className="h-4 w-4" />
                  RSI 指标 (14)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">RSI 值</span>
                    <span className={`text-2xl font-bold ${
                      !currentRSI ? "" :
                      currentRSI > 70 ? "text-down" :
                      currentRSI < 30 ? "text-up" : ""
                    }`}>
                      {currentRSI?.toFixed(1) || "--"}
                    </span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all ${
                        !currentRSI ? "" :
                        currentRSI > 70 ? "bg-down" :
                        currentRSI < 30 ? "bg-up" : "bg-yellow-500"
                      }`}
                      style={{ width: `${currentRSI || 0}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>超卖 30</span>
                    <span>超买 70</span>
                  </div>
                  <div className="pt-2 border-t">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-muted-foreground">信号</span>
                      <Badge variant={
                        getRSISignal() === "超买" ? "destructive" :
                        getRSISignal() === "超卖" ? "default" : "outline"
                      }>
                        {getRSISignal()}
                      </Badge>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* MACD指标 */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <BarChart3 className="h-4 w-4" />
                MACD 指标 (12, 26, 9)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-4 gap-4">
                <div className="space-y-0.5">
                  <p className="text-xs text-muted-foreground">DIF (快线)</p>
                  <p className={`text-lg font-medium ${
                    (currentMACD || 0) > 0 ? "text-up" : "text-down"
                  }`}>
                    {currentMACD?.toFixed(4) || "--"}
                  </p>
                </div>
                <div className="space-y-0.5">
                  <p className="text-xs text-muted-foreground">DEA (慢线)</p>
                  <p className={`text-lg font-medium ${
                    (currentSignal || 0) > 0 ? "text-up" : "text-down"
                  }`}>
                    {currentSignal?.toFixed(4) || "--"}
                  </p>
                </div>
                <div className="space-y-0.5">
                  <p className="text-xs text-muted-foreground">MACD 柱</p>
                  <p className={`text-lg font-medium ${
                    (currentHistogram || 0) > 0 ? "text-up" : "text-down"
                  }`}>
                    {currentHistogram?.toFixed(4) || "--"}
                  </p>
                </div>
                <div className="space-y-0.5">
                  <p className="text-xs text-muted-foreground">信号</p>
                  <Badge variant={
                    getMACDSignal() === "金叉买入" ? "default" :
                    getMACDSignal() === "死叉卖出" ? "destructive" : "outline"
                  }>
                    {getMACDSignal()}
                  </Badge>
                </div>
              </div>

              {/* MACD 柱状图 */}
              <div className="mt-4">
                <div className="flex items-end gap-1 h-16 overflow-hidden">
                  {macdData.histogram.slice(-30).map((val, i) => (
                    <div
                      key={i}
                      className="flex-1 min-w-[4px] max-w-[12px]"
                      style={{
                        height: `${Math.min(Math.abs(val || 0) * 20, 100)}%`,
                        backgroundColor: (val || 0) > 0 ? "var(--color-up)" : "var(--color-down)",
                      }}
                    />
                  ))}
                </div>
                <div className="flex justify-between text-xs text-muted-foreground mt-1">
                  <span>30天前</span>
                  <span>今天</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 统计信息 */}
          <div className="grid gap-4 md:grid-cols-5">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">最新价</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {chartData[chartData.length - 1]?.close.toFixed(2) || "--"}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">涨跌幅</CardTitle>
              </CardHeader>
              <CardContent>
                <div className={`text-2xl font-bold ${
                  (chartData.length > 1 && chartData[chartData.length - 1].close >= chartData[chartData.length - 2].close)
                    ? "text-up" : "text-down"
                }`}>
                  {chartData.length > 1 ? (
                    <>
                      {(
                        ((chartData[chartData.length - 1].close - chartData[chartData.length - 2].close) /
                          chartData[chartData.length - 2].close) *
                        100
                      ).toFixed(2)}
                      %
                    </>
                  ) : (
                    "--"
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">20日最高</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-up">
                  {high20 != null ? high20.toFixed(2) : "--"}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">20日最低</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-down">
                  {low20 != null ? low20.toFixed(2) : "--"}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">成交额</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {(chartData.slice(-5).reduce((sum, d) => sum + d.volume, 0) / 100000000).toFixed(1)}亿
                </div>
              </CardContent>
            </Card>
          </div>

          {/* 原始数据表 */}
          <Card>
            <CardHeader>
              <CardTitle>原始数据</CardTitle>
              <CardDescription>最近 20 个交易日数据</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>日期</TableHead>
                      <TableHead className="text-right">开盘</TableHead>
                      <TableHead className="text-right">最高</TableHead>
                      <TableHead className="text-right">最低</TableHead>
                      <TableHead className="text-right">收盘</TableHead>
                      <TableHead className="text-right">涨跌幅</TableHead>
                      <TableHead className="text-right">成交量</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {chartData.slice(-20).reverse().map((d, i) => {
                      const prevClose = i < chartData.slice(-20).length - 1
                        ? chartData[chartData.length - 2 - i]?.close
                        : d.open
                      const change = prevClose ? ((d.close - prevClose) / prevClose) * 100 : 0

                      return (
                        <TableRow key={d.time}>
                          <TableCell>{new Date(d.time * 1000).toLocaleDateString()}</TableCell>
                          <TableCell className="text-right">{d.open.toFixed(2)}</TableCell>
                          <TableCell className="text-right">{d.high.toFixed(2)}</TableCell>
                          <TableCell className="text-right">{d.low.toFixed(2)}</TableCell>
                          <TableCell className="text-right">{d.close.toFixed(2)}</TableCell>
                          <TableCell className={`text-right ${change >= 0 ? "text-up" : "text-down"}`}>
                            {change >= 0 ? "+" : ""}{change.toFixed(2)}%
                          </TableCell>
                          <TableCell className="text-right">{(d.volume / 10000).toFixed(0)}万</TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {/* 技术指标说明 */}
          <InstructionsPanel
            title="技术指标说明"
            description="K线图常用技术指标解读"
            instructions={[
              ...commonInstructions.rsi,
              ...commonInstructions.macd,
              ...commonInstructions.bollinger,
            ]}
            icon="info"
            defaultExpanded={false}
          />
        </>
      )}
    </div>
  )
}
