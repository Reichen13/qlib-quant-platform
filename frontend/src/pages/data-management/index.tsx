// 数据管理页面 - 数据更新与状态检查
import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Database, RefreshCw, CheckCircle, XCircle, Clock, Loader2, AlertCircle } from "lucide-react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useAppStore } from "@/stores/app-store"
import { UpdateProgress } from "@/components/features/update-progress"

export function DataManagementPage() {
  const dataManagementParams = useAppStore((s) => s.dataManagementParams)
  const setDataManagementParams = useAppStore((s) => s.setDataManagementParams)
  const isUpdating = dataManagementParams.isUpdating
  const updateSteps = dataManagementParams.updateSteps
  const overallProgress = dataManagementParams.overallProgress
  const updateTaskId = dataManagementParams.updateTaskId
  const [adminApiKey, setAdminApiKey] = useState(() => localStorage.getItem("qlib-admin-api-key") || "")
  const [repairStale, setRepairStale] = useState(false)
  const queryClient = useQueryClient()

  // 获取数据状态
  const { data: dataStatus, isLoading, refetch } = useQuery({
    queryKey: ["data", "status"],
    queryFn: () => api.data.status(),
    staleTime: 5 * 60 * 1000, // 5分钟内不重新获取
  })

  // 获取数据更新日志
  const { data: dataLogs } = useQuery({
    queryKey: ["data", "logs"],
    queryFn: () => api.data.logs(),
    staleTime: 2 * 60 * 1000,
  })

  const buildUpdateSteps = (status: any) => {
    const progress = status?.progress ?? 5
    const message = status?.message || "正在更新 Qlib 数据"
    if (status?.status === "completed") {
      return [
        { id: "request", name: "发送更新请求", status: "completed" as const, progress: 100, message: "更新任务已启动", endTime: status.started_at },
        { id: "process", name: "处理数据", status: "completed" as const, progress: 100, message: "数据处理完成", endTime: status.finished_at },
        { id: "save", name: "保存到数据库", status: "completed" as const, progress: 100, message, endTime: status.finished_at },
      ]
    }
    if (status?.status === "failed") {
      return [
        { id: "request", name: "发送更新请求", status: "completed" as const, progress: 100, message: "更新任务已启动", endTime: status.started_at },
        { id: "process", name: "处理数据", status: "failed" as const, progress: 100, message, endTime: status.finished_at },
        { id: "save", name: "保存到数据库", status: "pending" as const, progress: 0 },
      ]
    }
    return [
      { id: "request", name: "发送更新请求", status: "completed" as const, progress: 100, message: "更新任务已启动", startTime: status?.started_at },
      { id: "process", name: "处理数据", status: "running" as const, progress, message, startTime: status?.started_at },
      { id: "save", name: "保存到数据库", status: "pending" as const, progress: 0 },
    ]
  }

  useQuery({
    queryKey: ["data", "update-progress", updateTaskId],
    queryFn: async () => {
      const progress = await api.data.updateProgress(updateTaskId!)
      const done = progress.status === "completed" || progress.status === "failed"
      setDataManagementParams({
        isUpdating: progress.status === "running",
        overallProgress: progress.progress ?? (done ? 100 : 5),
        updateSteps: buildUpdateSteps(progress),
      })
      if (done) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["data", "status"] }),
          queryClient.invalidateQueries({ queryKey: ["data", "logs"] }),
        ])
      }
      return progress
    },
    enabled: !!updateTaskId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === "running" ? 5000 : false
    },
    retry: false,
  })

  const handleCheckStatus = () => {
    refetch()
  }

  const handleAdminKeyChange = (value: string) => {
    setAdminApiKey(value)
    if (value) {
      localStorage.setItem("qlib-admin-api-key", value)
    } else {
      localStorage.removeItem("qlib-admin-api-key")
    }
  }

  const handleUpdate = async (type: "stocks" | "etf" | "index" | "all") => {
    setDataManagementParams({
      updateTaskId: null,
      isUpdating: true,
      updateSteps: [
      { id: "request", name: "发送更新请求", status: "running", progress: 30, message: `正在请求${type === 'all' ? '全量' : type}数据更新...`, startTime: new Date().toISOString() },
      { id: "process", name: "处理数据", status: "pending", progress: 0 },
      { id: "save", name: "保存到数据库", status: "pending", progress: 0 },
      ],
      overallProgress: 10,
    })

    try {
      const result = await api.data.update(type, { rebuildStale: repairStale })
      const taskId = result.task_id
      setDataManagementParams({
        updateTaskId: taskId,
        isUpdating: true,
        updateSteps: [
        { id: "request", name: "发送更新请求", status: "completed", progress: 100, message: "更新任务已启动", startTime: new Date(Date.now() - 1000).toISOString(), endTime: new Date().toISOString() },
        { id: "process", name: "处理数据", status: "running", progress: result.progress || 5, message: result.message || "正在更新 Qlib 数据", startTime: new Date().toISOString() },
        { id: "save", name: "保存到数据库", status: "pending", progress: 0 },
        ],
        overallProgress: result.progress || 5,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : "更新失败"
      const failedSteps = updateSteps.length > 0
        ? updateSteps
        : [
          { id: "request", name: "发送更新请求", status: "failed" as const, progress: 100, message },
          { id: "process", name: "处理数据", status: "pending" as const, progress: 0 },
          { id: "save", name: "保存到数据库", status: "pending" as const, progress: 0 },
        ]
      setDataManagementParams({
        isUpdating: false,
        overallProgress: 100,
        updateSteps: failedSteps.map((s: any) => (
          s.status === "running" ? { ...s, status: "failed" as const, message } : s
        )),
      })
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
              更新 Qlib 数据
            </>
          )}
        </Button>
        <Button variant="outline" onClick={() => handleUpdate("stocks")} disabled={isUpdating}>
          更新股票数据
        </Button>
        <Button variant="outline" onClick={() => handleUpdate("etf")} disabled={true}>
          ETF 更新未接入
        </Button>
        <Button variant="outline" onClick={() => handleUpdate("index")} disabled={true}>
          指数更新未接入
        </Button>
      </div>

      <label className="flex max-w-fit items-center gap-2 text-sm text-muted-foreground">
        <input
          type="checkbox"
          checked={repairStale}
          onChange={(event) => setRepairStale(event.target.checked)}
          disabled={isUpdating}
          className="h-4 w-4"
        />
        修复已有 0 值历史 K 线
      </label>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">服务器管理 Key</CardTitle>
          <CardDescription>用于数据更新、回测、风险管理等受保护操作；不会用于 LLM 模型调用。</CardDescription>
        </CardHeader>
        <CardContent>
          <Input
            type="password"
            value={adminApiKey}
            onChange={(event) => handleAdminKeyChange(event.target.value)}
            placeholder="请输入服务器 API_KEY"
            autoComplete="off"
          />
        </CardContent>
      </Card>

      {/* 更新进度 */}
      {(isUpdating || overallProgress === 100) && (
        <UpdateProgress
          steps={updateSteps}
          overallProgress={overallProgress}
          isRunning={isUpdating}
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
                <span className="font-medium">Qlib 本地数据</span>
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
            <CardDescription>ETF/指数暂按 Qlib 状态代理展示，尚未接入独立更新</CardDescription>
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
                <span className="font-medium">Qlib 状态代理</span>
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
            <CardDescription>ETF/指数暂按 Qlib 状态代理展示，尚未接入独立更新</CardDescription>
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
                <span className="font-medium">Qlib 状态代理</span>
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
                <TableCell>Qlib cn_data</TableCell>
                <TableCell>交易日收盘后</TableCell>
                <TableCell>A股全市场 (3800+)</TableCell>
                <TableCell>2020年起</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>ETF 行情</TableCell>
                <TableCell>暂未接入独立更新</TableCell>
                <TableCell>交易日收盘后</TableCell>
                <TableCell>待接入独立更新</TableCell>
                <TableCell>暂无可靠数据</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>指数行情</TableCell>
                <TableCell>暂未接入独立更新</TableCell>
                <TableCell>交易日收盘后</TableCell>
                <TableCell>待接入独立更新</TableCell>
                <TableCell>暂无可靠数据</TableCell>
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
            {(dataLogs?.logs || []).map((log: any, i: number) => (
              <div key={i} className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                <div className="flex items-center gap-3">
                  {log.type === "normal" || log.type === "success" ? (
                    <CheckCircle className="h-5 w-5 text-up" />
                  ) : log.type === "warning" ? (
                    <AlertCircle className="h-5 w-5 text-yellow-600" />
                  ) : (
                    <XCircle className="h-5 w-5 text-down" />
                  )}
                  <div className="space-y-0.5">
                    <p className="font-medium">{log.title}</p>
                    <p className="text-xs text-muted-foreground">{log.detail}</p>
                  </div>
                </div>
                <div className="text-right text-sm text-muted-foreground">
                  <p>{log.time}</p>
                </div>
              </div>
            ))}
            {(!dataLogs?.logs || dataLogs.logs.length === 0) && (
              <p className="text-sm text-muted-foreground text-center py-4">暂无数据更新记录，点击"检查状态"获取最新信息</p>
            )}
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
              <p className="font-medium text-xs">当前站点 /api</p>
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
          <p>• <strong>数据来源：</strong>Qlib 本地 cn_data；当前网页更新只接入股票日线数据</p>
          <p>• <strong>更新时间：</strong>建议在交易日收盘后（15:30 之后）更新数据</p>
          <p>• <strong>数据范围：</strong>A股股票日线；ETF、指数暂按 Qlib 状态代理展示，尚未接入独立更新</p>
          <p>• <strong>历史数据：</strong>支持从 2020-01-01 起的历史回测</p>
          <p>• <strong>命令行更新：</strong>也可以使用 Python 脚本手动更新数据</p>
        </CardContent>
      </Card>
    </div>
  )
}
