// 均值回归页面 - 超买超卖扫描
import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { TrendingDown, TrendingUp, AlertCircle, Search, Loader2, RefreshCw, Filter } from "lucide-react"
import { InstructionsPanel } from "@/components/features/instructions-panel"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"

// 扫描条件选项
const rsiThresholds = [
  { value: "70", label: "70 (标准)" },
  { value: "75", label: "75 (严格)" },
  { value: "80", label: "80 (极端)" },
]

const bollingerPeriods = [
  { value: "20", label: "20日" },
  { value: "10", label: "10日" },
  { value: "30", label: "30日" },
]

interface SignalItem {
  code: string
  name: string
  rsi: number
  bollingerPosition: number
  signal: string
  score: number
  strength: string
}

export function MeanReversionPage() {
  const [searchQuery, setSearchQuery] = useState("")
  const [rsiThreshold, setRsiThreshold] = useState("70")
  const [bollingerPeriod, setBollingerPeriod] = useState("20")
  const [scanType, setScanType] = useState<"both" | "rsi" | "bollinger">("both")
  const [isLoading, setIsLoading] = useState(false)

  // 从后端获取均值回归信号
  const { data: signalsData, isLoading: signalsLoading, refetch } = useQuery({
    queryKey: ["mean-reversion", "signals", rsiThreshold, bollingerPeriod],
    queryFn: () => api.meanReversion.scan({
      rsiThreshold: parseInt(rsiThreshold),
      bollingerPeriod: parseInt(bollingerPeriod),
    }),
  })

  // 使用后端数据
  const meanReversionSignals = signalsData?.signals?.length > 0
    ? signalsData.signals
    : []

  const filteredSignals = meanReversionSignals.filter(
    (s: SignalItem) =>
      s.name.includes(searchQuery) || s.code.includes(searchQuery)
  )

  // 根据扫描类型筛选
  const scannedSignals = filteredSignals.filter((s: SignalItem) => {
    if (scanType === "both") {
      return s.signal === "超买" || s.signal === "超卖"
    }
    if (scanType === "rsi") {
      return s.rsi > parseInt(rsiThreshold) || s.rsi < (100 - parseInt(rsiThreshold))
    }
    if (scanType === "bollinger") {
      return s.bollingerPosition > 0.8 || s.bollingerPosition < 0.2
    }
    return true
  })

  const overbought = scannedSignals.filter((s: SignalItem) => s.signal === "超买")
  const oversold = scannedSignals.filter((s: SignalItem) => s.signal === "超卖")
  const watch = scannedSignals.filter((s: SignalItem) => s.signal === "关注")

  const handleScan = async () => {
    setIsLoading(true)
    await refetch()
    setTimeout(() => setIsLoading(false), 500)
  }

  const getStrengthBadge = (strength: string) => {
    switch (strength) {
      case "强":
        return <Badge variant="destructive">强</Badge>
      case "中":
        return <Badge className="bg-yellow-600">中</Badge>
      case "弱":
        return <Badge variant="outline">弱</Badge>
      default:
        return <Badge variant="outline">{strength}</Badge>
    }
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <TrendingDown className="h-8 w-8 text-green-600" />
          均值回归
        </h1>
        <p className="text-muted-foreground">超买超卖扫描 - RSI + 布林带双重条件</p>
      </div>

      {/* 扫描参数配置 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-5 w-5" />
            扫描参数
          </CardTitle>
          <CardDescription>配置扫描条件参数</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-4">
            <div className="space-y-2">
              <Label>RSI 阈值</Label>
              <Select value={rsiThreshold} onValueChange={setRsiThreshold}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {rsiThresholds.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>布林带周期</Label>
              <Select value={bollingerPeriod} onValueChange={setBollingerPeriod}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {bollingerPeriods.map((p) => (
                    <SelectItem key={p.value} value={p.value}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>扫描类型</Label>
              <Select value={scanType} onValueChange={(v) => setScanType(v as any)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="both">双重条件</SelectItem>
                  <SelectItem value="rsi">仅 RSI</SelectItem>
                  <SelectItem value="bollinger">仅布林带</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>&nbsp;</Label>
              <Button onClick={handleScan} disabled={isLoading} className="w-full">
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    扫描中...
                  </>
                ) : (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    开始扫描
                  </>
                )}
              </Button>
            </div>
          </div>

          <div className="flex gap-2 mt-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="输入股票代码或名称"
                className="pl-9"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 统计概览 */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">超买信号</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-down">
              {overbought.length}
            </div>
            <p className="text-xs text-muted-foreground">
              RSI &gt; {rsiThreshold}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">超卖信号</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-up">
              {oversold.length}
            </div>
            <p className="text-xs text-muted-foreground">
              RSI &lt; {100 - parseInt(rsiThreshold)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">关注股票</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {watch.length}
            </div>
            <p className="text-xs text-muted-foreground">临界状态</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">平均 RSI</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {(filteredSignals.reduce((sum: number, s: SignalItem) => sum + s.rsi, 0) / filteredSignals.length).toFixed(1)}
            </div>
            <p className="text-xs text-muted-foreground">市场整体水平</p>
          </CardContent>
        </Card>
      </div>

      {/* 标签页 */}
      <Tabs defaultValue="overbought">
        <TabsList className="grid w-full max-w-md grid-cols-3">
          <TabsTrigger value="overbought">
            超买 ({overbought.length})
          </TabsTrigger>
          <TabsTrigger value="oversold">
            超卖 ({oversold.length})
          </TabsTrigger>
          <TabsTrigger value="watch">
            关注 ({watch.length})
          </TabsTrigger>
        </TabsList>

        {/* 超买信号 */}
        <TabsContent value="overbought">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-down" />
                超买信号
                <Badge variant="destructive">{overbought.length}</Badge>
              </CardTitle>
              <CardDescription>价格可能回调，建议谨慎追高</CardDescription>
            </CardHeader>
            <CardContent>
              {signalsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : overbought.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  暂无超买信号
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>代码</TableHead>
                      <TableHead>名称</TableHead>
                      <TableHead className="text-right">RSI</TableHead>
                      <TableHead className="text-right">布林带位置</TableHead>
                      <TableHead className="text-right">信号强度</TableHead>
                      <TableHead className="text-right">评分</TableHead>
                      <TableHead className="text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {overbought.map((stock: SignalItem) => (
                      <TableRow key={stock.code}>
                        <TableCell className="font-medium">{stock.code}</TableCell>
                        <TableCell>{stock.name}</TableCell>
                        <TableCell className="text-right text-down font-medium">
                          {stock.rsi.toFixed(1)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Badge variant={stock.bollingerPosition > 0.8 ? "destructive" : "outline"}>
                            {(stock.bollingerPosition * 100).toFixed(0)}%
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          {getStrengthBadge(stock.strength)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Badge variant="outline">{stock.score}</Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <a href={`/quote?stock=${stock.code}`} className="text-sm text-primary hover:underline">
                            查看详情
                          </a>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* 超卖信号 */}
        <TabsContent value="oversold">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingDown className="h-5 w-5 text-up" />
                超卖信号
                <Badge variant="default">{oversold.length}</Badge>
              </CardTitle>
              <CardDescription>价格可能反弹，可关注机会</CardDescription>
            </CardHeader>
            <CardContent>
              {signalsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : oversold.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  暂无超卖信号
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>代码</TableHead>
                      <TableHead>名称</TableHead>
                      <TableHead className="text-right">RSI</TableHead>
                      <TableHead className="text-right">布林带位置</TableHead>
                      <TableHead className="text-right">信号强度</TableHead>
                      <TableHead className="text-right">评分</TableHead>
                      <TableHead className="text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {oversold.map((stock: SignalItem) => (
                      <TableRow key={stock.code}>
                        <TableCell className="font-medium">{stock.code}</TableCell>
                        <TableCell>{stock.name}</TableCell>
                        <TableCell className="text-right text-up font-medium">
                          {stock.rsi.toFixed(1)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Badge variant={stock.bollingerPosition < 0.2 ? "default" : "outline"}>
                            {(stock.bollingerPosition * 100).toFixed(0)}%
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          {getStrengthBadge(stock.strength)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Badge variant="outline">{stock.score}</Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <a href={`/quote?stock=${stock.code}`} className="text-sm text-primary hover:underline">
                            查看详情
                          </a>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* 关注 */}
        <TabsContent value="watch">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertCircle className="h-5 w-5 text-yellow-600" />
                关注列表
                <Badge className="bg-yellow-600">{watch.length}</Badge>
              </CardTitle>
              <CardDescription>接近临界状态的股票</CardDescription>
            </CardHeader>
            <CardContent>
              {watch.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  暂无关注股票
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>代码</TableHead>
                      <TableHead>名称</TableHead>
                      <TableHead className="text-right">RSI</TableHead>
                      <TableHead className="text-right">布林带位置</TableHead>
                      <TableHead className="text-right">信号强度</TableHead>
                      <TableHead className="text-right">评分</TableHead>
                      <TableHead className="text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {watch.map((stock: SignalItem) => (
                      <TableRow key={stock.code}>
                        <TableCell className="font-medium">{stock.code}</TableCell>
                        <TableCell>{stock.name}</TableCell>
                        <TableCell className="text-right font-medium">
                          {stock.rsi.toFixed(1)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Badge variant="outline">
                            {(stock.bollingerPosition * 100).toFixed(0)}%
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          {getStrengthBadge(stock.strength)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Badge variant="outline">{stock.score}</Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <a href={`/quote?stock=${stock.code}`} className="text-sm text-primary hover:underline">
                            查看详情
                          </a>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* 策略说明 */}
      <InstructionsPanel
        title="均值回归策略说明"
        description="RSI + 布林带双重指标扫描超买超卖机会"
        icon="warning"
        defaultExpanded={false}
        instructions={[
          {
            title: "RSI 指标",
            description: `相对强弱指数，当前阈值设置为 ${rsiThreshold}。RSI > ${rsiThreshold} 表示超买，RSI < ${100 - parseInt(rsiThreshold)} 表示超卖`,
          },
          {
            title: "布林带指标",
            description: `布林带周期为 ${bollingerPeriod} 日，价格突破上轨可能回调，跌破下轨可能反弹`,
          },
          {
            title: "双重条件扫描",
            description: "当 RSI 和布林带同时触发信号时，信号强度为「强」，仅单一指标触发为「中」",
          },
          {
            title: "操作建议",
            description: "超买信号建议减仓或规避，超卖信号可关注反弹机会。注意止损，技术指标存在失效可能",
          },
        ]}
      />
    </div>
  )
}
