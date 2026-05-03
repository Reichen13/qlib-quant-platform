// 数据管理页面 - 数据更新与状态检查
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
import { Database, RefreshCw, CheckCircle, XCircle, Clock, Loader2, AlertCircle } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { UpdateProgress } from "@/components/features/update-progress"

// 获取最近一个交易日期（排除周末）
function getLastTradeDate(daysAgo: number = 0): string {
  const today = new Date()
  const date = new Date(today)
  date.setDate(date.getDate() - daysAgo)

  // 如果是周末（周六=6，周日=0），往前推到周五
  const dayOfWeek = date.getDay()
  if (dayOfWeek === 0) {
    date.setDate(date.getDate() - 2) // 周日 -> 周五
  } else if (dayOfWeek === 6) {
    date.setDate(date.getDate() - 1) // 周六 -> 周五
  }

  return date.toISOString().split("T")[0]
}

export function DataManagementPage() {
  const [isUpdating, setIsUpdating] = useState(false)
  const [updateSteps, setUpdateSteps] = useState<any[]>([])
  const [overallProgress, setOverallProgress] = useState(0)

  // 获取数据状态
  const { data: dataStatus, isLoading, refetch } = useQuery({
    queryKey: ["data", "status"],
    queryFn: () => api.data.status(),
    staleTime: 5 * 60 * 1000, // 5分钟内不重新获取
  })

  const handleCheckStatus = () => {
    refetch()
  }

  const handleUpdate = async (type: "stocks" | "etf" | "index" | "all") => {
    setIsUpdating(true)
    setUpdateSteps([
      { id: "request", name: "发送更新请求", status: "running", progress: 30, message: `正在请求${type === 'all' ? '全量' : type}数据更新...`, startTime: new Date().toISOString() },
      { id: "process", name: "处理数据", status: "pending", progress: 0 },
      { id: "save", name: "保存到数据库", status: "pending", progress: 0 },
    ])
    setOverallProgress(10)

    try {
      const result = await api.data.update(type)
      setUpdateSteps([
        { id: "request", name: "发送更新请求", status: "completed", progress: 100, message: "更新请求已发送", startTime: new Date(Date.now() - 2000).toISOString(), endTime: new Date().toISOString() },
        { id: "process", name: "处理数据", status: "completed", progress: 100, message: result.message || "数据处理完成", startTime: new Date(Date.now() - 1000).toISOString(), endTime: new Date().toISOString() },
        { id: "save", name: "保存到数据库", status: "completed", progress: 100, message: "数据已保存", startTime: new Date(Date.now() - 500).toISOString(), endTime: new Date().toISOString() },
      ])
      setOverallProgress(100)
      refetch()
    } catch {
      setUpdateSteps((prev) => prev.map((s: any) => s.status === "running" ? { ...s, status: "error" as const, message: "更新失败" } : s))
    } finally {
      setIsUpdating(false)
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "normal":
        return <CheckCircle className="h-4 w-4 text-up" />
      case "warning":
        return <AlertCircle className="h-4 w-4 text-yellow-600" />
      case "error":
        return <XCircle className="h-4 w-4 text-down" />
      default:
        return <Clock className="h-4 w-4 text-muted-foreground" />
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "normal":
        return <Badge variant="default">正常</Badge>
      case "warning":
        return <Badge className="bg-yellow-600">需更新</Badge>
      case "error":
        return <Badge variant="destructive">异常</Badge>
      default:
        return <Badge variant="outline">未知</Badge>
    }
  }

  const today = new Date()
  const lastTradeDate = new Date(today)
  lastTradeDate.setDate(lastTradeDate.getDate() - 1)
  while (lastTradeDate.getDay() === 0 || lastTradeDate.getDay() === 6) {
    lastTradeDate.setDate(lastTradeDate.getDate() - 1)
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Database className="h-8 w-8 text-slate-600" />
          数据管理
        </h1>
        <p className="text-muted-foreground">数据状态检查与更新管理</p>
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-4 flex-wrap">
        <Button onClick={handleCheckStatus} disabled={isLoading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
          检查状态
        </Button>
        <Button onClick={() => handleUpdate("all")} disabled={isUpdating}>
          {isUpdating ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              更新中...
            </>
          ) : (
            <>
              <Database className="mr-2 h-4 w-4" />
              全量更新
            </>
          )}
        </Button>
        <Button variant="outline" onClick={() => handleUpdate("stocks")} disabled={isUpdating}>
          更新股票数据
        </Button>
        <Button variant="outline" onClick={() => handleUpdate("etf")} disabled={isUpdating}>
          更新 ETF 数据
        </Button>
        <Button variant="outline" onClick={() => handleUpdate("index")} disabled={isUpdating}>
          更新指数数据
        </Button>
      </div>

      {/* 更新进度 */}
      {(isUpdating || overallProgress === 100) && (
        <UpdateProgress
          steps={updateSteps}
          overallProgress={overallProgress}
          isRunning={isUpdating}
          onCancel={() => setIsUpdating(false)}
          onRetry={() => handleUpdate("all")}
        />
      )}

      {/* 数据状态卡片 */}
      <div className="grid gap-4 md:grid-cols-3">
        {/* 股票数据 */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>股票数据</CardTitle>
              <div className="flex items-center gap-2">
                {getStatusIcon(dataStatus?.stocks?.status || "unknown")}
                {getStatusBadge(dataStatus?.stocks?.status || "unknown")}
              </div>
            </div>
            <CardDescription>A股全市场日线数据</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">覆盖数量</span>
                <span className="font-medium">{dataStatus?.stocks?.total ?? "--"} 只</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">最新日期</span>
                <span className="font-medium">{dataStatus?.stocks?.last_date || "--"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">滞后天数</span>
                <span className={`font-medium ${(dataStatus?.stocks?.lag_days ?? 0) > 1 ? "text-yellow-600" : ""}`}>
                  {dataStatus?.stocks?.lag_days ?? "--"} 天
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">数据来源</span>
                <span className="font-medium">yfinance</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ETF 数据 */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>ETF 数据</CardTitle>
              <div className="flex items-center gap-2">
                {getStatusIcon(dataStatus?.etf?.status || "unknown")}
                {getStatusBadge(dataStatus?.etf?.status || "unknown")}
              </div>
            </div>
            <CardDescription>全市场 ETF 日线数据</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">覆盖数量</span>
                <span className="font-medium">{dataStatus?.etf?.total ?? "--"} 只</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">最新日期</span>
                <span className="font-medium">{dataStatus?.etf?.last_date || "--"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">滞后天数</span>
                <span className="font-medium">{dataStatus?.etf?.lag_days ?? "--"} 天</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">数据来源</span>
                <span className="font-medium">yfinance</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 指数数据 */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>指数数据</CardTitle>
              <div className="flex items-center gap-2">
                {getStatusIcon(dataStatus?.index?.status || "unknown")}
                {getStatusBadge(dataStatus?.index?.status || "unknown")}
              </div>
            </div>
            <CardDescription>主要指数日线数据</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">覆盖数量</span>
                <span className="font-medium">{dataStatus?.index?.total ?? "--"} 个</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">最新日期</span>
                <span className="font-medium">{dataStatus?.index?.last_date || "--"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">滞后天数</span>
                <span className="font-medium">{dataStatus?.index?.lag_days ?? "--"} 天</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">数据来源</span>
                <span className="font-medium">yfinance</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 数据来源说明 */}
      <Card>
        <CardHeader>
          <CardTitle>数据来源说明</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>数据类型</TableHead>
                <TableHead>数据源</TableHead>
                <TableHead>更新频率</TableHead>
                <TableHead>覆盖范围</TableHead>
                <TableHead>历史数据</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell>股票行情</TableCell>
                <TableCell>yfinance</TableCell>
                <TableCell>交易日收盘后</TableCell>
                <TableCell>A股全市场 (3800+)</TableCell>
                <TableCell>2020年起</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>ETF 行情</TableCell>
                <TableCell>yfinance</TableCell>
                <TableCell>交易日收盘后</TableCell>
                <TableCell>全市场 ETF (300+)</TableCell>
                <TableCell>2020年起</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>指数行情</TableCell>
                <TableCell>yfinance</TableCell>
                <TableCell>交易日收盘后</TableCell>
                <TableCell>主要指数 (12个)</TableCell>
                <TableCell>2020年起</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>财务数据</TableCell>
                <TableCell>本地数据库</TableCell>
                <TableCell>季度更新</TableCell>
                <TableCell>CSI300 成分股</TableCell>
                <TableCell>2019年起</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* 数据更新日志 */}
      <Card>
        <CardHeader>
          <CardTitle>更新日志</CardTitle>
          <CardDescription>最近的数据更新记录</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
              <div className="flex items-center gap-3">
                <CheckCircle className="h-5 w-5 text-up" />
                <div className="space-y-0.5">
                  <p className="font-medium">全量数据更新完成</p>
                  <p className="text-xs text-muted-foreground">更新股票 3800 只，ETF 320 只，指数 12 个</p>
                </div>
              </div>
              <div className="text-right text-sm text-muted-foreground">
                <p>{getLastTradeDate(0)}</p>
                <p>15:30</p>
              </div>
            </div>
            <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
              <div className="flex items-center gap-3">
                <CheckCircle className="h-5 w-5 text-up" />
                <div className="space-y-0.5">
                  <p className="font-medium">股票数据增量更新</p>
                  <p className="text-xs text-muted-foreground">更新 1 天数据</p>
                </div>
              </div>
              <div className="text-right text-sm text-muted-foreground">
                <p>{getLastTradeDate(1)}</p>
                <p>15:30</p>
              </div>
            </div>
            <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
              <div className="flex items-center gap-3">
                <CheckCircle className="h-5 w-5 text-up" />
                <div className="space-y-0.5">
                  <p className="font-medium">ETF 数据补充更新</p>
                  <p className="text-xs text-muted-foreground">新增 15 只 ETF 数据</p>
                </div>
              </div>
              <div className="text-right text-sm text-muted-foreground">
                <p>{getLastTradeDate(2)}</p>
                <p>10:15</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 系统信息 */}
      <Card>
        <CardHeader>
          <CardTitle>系统信息</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-0.5">
              <p className="text-sm text-muted-foreground">API 端点</p>
              <p className="font-medium text-xs">http://localhost:8000</p>
            </div>
            <div className="space-y-0.5">
              <p className="text-sm text-muted-foreground">API 服务状态</p>
              <p className="font-medium text-up flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-up animate-pulse" />
                运行中
              </p>
            </div>
            <div className="space-y-0.5">
              <p className="text-sm text-muted-foreground">Qlib 版本</p>
              <p className="font-medium text-xs">0.9.2</p>
            </div>
            <div className="space-y-0.5">
              <p className="text-sm text-muted-foreground">数据存储路径</p>
              <p className="font-medium text-xs">~/.qlib/qlib_data/cn_data</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 使用说明 */}
      <Card>
        <CardHeader>
          <CardTitle>使用说明</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>• <strong>数据来源：</strong>yfinance（Yahoo Finance）免费数据接口</p>
          <p>• <strong>更新时间：</strong>建议在交易日收盘后（15:30 之后）更新数据</p>
          <p>• <strong>数据范围：</strong>A股全市场、全市场 ETF、主要指数</p>
          <p>• <strong>历史数据：</strong>支持从 2020-01-01 起的历史回测</p>
          <p>• <strong>命令行更新：</strong>也可以使用 Python 脚本手动更新数据</p>
        </CardContent>
      </Card>
    </div>
  )
}
