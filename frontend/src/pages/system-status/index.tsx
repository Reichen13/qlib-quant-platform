import { useQuery } from "@tanstack/react-query"
import { Activity, AlertTriangle, CheckCircle2, Clock, Download, ExternalLink, MonitorCog, RefreshCw } from "lucide-react"
import { api } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

function statusBadge(status?: string) {
  if (status === "healthy" || status === "completed") return <Badge>正常</Badge>
  if (status === "running") return <Badge className="bg-blue-600">运行中</Badge>
  if (status === "failed") return <Badge variant="destructive">失败</Badge>
  return <Badge variant="outline">需检查</Badge>
}

function yesNo(value: boolean) {
  return value ? "是" : "否"
}

export function SystemStatusPage() {
  const environment = useQuery({
    queryKey: ["system-environment"],
    queryFn: () => api.system.environment(),
  })
  const tasks = useQuery({
    queryKey: ["system-tasks"],
    queryFn: () => api.system.tasks(),
    refetchInterval: 10_000,
  })

  const env = environment.data
  const taskRows = tasks.data?.tasks || []

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
            <MonitorCog className="h-7 w-7 text-primary" />
            系统状态
          </h1>
          <p className="text-muted-foreground">本地环境自检、数据目录检查和长任务汇总。</p>
        </div>
        <Button
          variant="outline"
          onClick={() => {
            environment.refetch()
            tasks.refetch()
          }}
        >
          <RefreshCw className="mr-2 h-4 w-4" />
          刷新
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4" /> 环境状态
            </CardTitle>
            <CardDescription>Python、依赖和前端安装状态</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">整体状态</span>
              {statusBadge(env?.overall_status)}
            </div>
            <div className="text-sm">Python：{env?.python?.version || "--"}</div>
            <div className="text-xs text-muted-foreground break-all">{env?.python?.executable || "--"}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" /> Qlib 数据
            </CardTitle>
            <CardDescription>本地市场数据目录</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">目录完整</span>
              {statusBadge(env?.qlib_data?.status)}
            </div>
            <div>最新日历：{env?.qlib_data?.latest_calendar_date || "--"}</div>
            <div>标的目录数：{env?.qlib_data?.feature_count ?? "--"}</div>
            <div className="text-xs text-muted-foreground break-all">{env?.qlib_data?.path || "--"}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4" /> 提醒
            </CardTitle>
            <CardDescription>需要人工处理的问题</CardDescription>
          </CardHeader>
          <CardContent>
            {env?.warnings?.length ? (
              <ul className="list-disc pl-5 text-sm space-y-1">
                {env.warnings.map((warning: string) => <li key={warning}>{warning}</li>)}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">暂无明显环境问题。</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-4 w-4" /> 任务中心
          </CardTitle>
          <CardDescription>当前先汇总回测任务，后续可扩展到因子分析、数据更新和 AI 分析。</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>类型</TableHead>
                <TableHead>任务 ID</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>进度</TableHead>
                <TableHead>更新时间</TableHead>
                <TableHead>错误</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {taskRows.length ? taskRows.map((task: any) => (
                <TableRow key={`${task.type}-${task.task_id}`}>
                  <TableCell>{task.type}</TableCell>
                  <TableCell className="font-mono text-xs max-w-[220px] truncate">{task.task_id}</TableCell>
                  <TableCell>{statusBadge(task.status)}</TableCell>
                  <TableCell>{task.progress ?? 0}%</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{task.updated_at || "--"}</TableCell>
                  <TableCell className="text-xs text-red-600 max-w-[260px] truncate">{task.error || "--"}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      {task.detail_url && (
                        <Button variant="outline" size="sm" asChild>
                          <a href={task.detail_url} target="_blank" rel="noreferrer">
                            <ExternalLink className="mr-1 h-3 w-3" />
                            打开
                          </a>
                        </Button>
                      )}
                      {task.report_url && (
                        <Button variant="outline" size="sm" asChild>
                          <a href={task.report_url} download>
                            <Download className="mr-1 h-3 w-3" />
                            报告
                          </a>
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              )) : (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                    暂无任务记录。
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>依赖检查</CardTitle>
          <CardDescription>关键 Python 包是否可导入</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2 md:grid-cols-3 text-sm">
          {Object.entries(env?.dependencies || {}).map(([name, ok]) => (
            <div key={name} className="flex items-center justify-between rounded-lg border px-3 py-2">
              <span>{name}</span>
              <span className={ok ? "text-green-600" : "text-red-600"}>{yesNo(Boolean(ok))}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
