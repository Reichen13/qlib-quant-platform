// 更新进度组件 - 显示数据更新进度
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { CheckCircle, Loader2, XCircle, Clock } from "lucide-react"

export interface UpdateStep {
  id: string
  name: string
  status: "pending" | "running" | "completed" | "failed"
  progress: number
  message?: string
  startTime?: string
  endTime?: string
}

export interface UpdateProgressProps {
  steps: UpdateStep[]
  overallProgress: number
  isRunning: boolean
  onCancel?: () => void
  onRetry?: () => void
}

export function UpdateProgress({
  steps,
  overallProgress,
  isRunning,
  onCancel,
  onRetry,
}: UpdateProgressProps) {
  const getStatusIcon = (status: UpdateStep["status"]) => {
    switch (status) {
      case "pending":
        return <Clock className="h-4 w-4 text-muted-foreground" />
      case "running":
        return <Loader2 className="h-4 w-4 text-primary animate-spin" />
      case "completed":
        return <CheckCircle className="h-4 w-4 text-up" />
      case "failed":
        return <XCircle className="h-4 w-4 text-down" />
    }
  }

  const getStatusBadge = (status: UpdateStep["status"]) => {
    switch (status) {
      case "pending":
        return <Badge variant="outline">等待中</Badge>
      case "running":
        return <Badge className="bg-blue-600">进行中</Badge>
      case "completed":
        return <Badge variant="default">已完成</Badge>
      case "failed":
        return <Badge variant="destructive">失败</Badge>
    }
  }

  const completedCount = steps.filter((s) => s.status === "completed").length
  const failedCount = steps.filter((s) => s.status === "failed").length

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>更新进度</CardTitle>
          <Badge variant={overallProgress === 100 ? "default" : "outline"}>
            {overallProgress.toFixed(0)}%
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 总体进度条 */}
        <div>
          <div className="flex justify-between text-sm mb-2">
            <span>总体进度</span>
            <span>
              {completedCount}/{steps.length} 步骤完成
              {failedCount > 0 && ` (${failedCount} 失败)`}
            </span>
          </div>
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary transition-all duration-300"
              style={{ width: `${overallProgress}%` }}
            />
          </div>
        </div>

        {/* 详细步骤 */}
        <div className="space-y-3">
          {steps.map((step) => (
            <div key={step.id} className="border rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  {getStatusIcon(step.status)}
                  <span className="font-medium text-sm">{step.name}</span>
                </div>
                {getStatusBadge(step.status)}
              </div>

              {step.status === "running" && step.progress > 0 && (
                <div className="mt-2">
                  <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all duration-200"
                      style={{ width: `${step.progress}%` }}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {step.message || `${step.progress}%`}
                  </p>
                </div>
              )}

              {step.message && step.status !== "running" && (
                <p className={`text-xs mt-1 ${
                  step.status === "failed" ? "text-down" : "text-muted-foreground"
                }`}>
                  {step.message}
                </p>
              )}

              {(step.startTime || step.endTime) && (
                <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
                  {step.startTime && (
                    <span>开始: {new Date(step.startTime).toLocaleTimeString()}</span>
                  )}
                  {step.endTime && (
                    <span>结束: {new Date(step.endTime).toLocaleTimeString()}</span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-2 pt-2">
          {isRunning && onCancel && (
            <Button variant="outline" size="sm" onClick={onCancel}>
              取消更新
            </Button>
          )}
          {!isRunning && failedCount > 0 && onRetry && (
            <Button size="sm" onClick={onRetry}>
              重试失败项
            </Button>
          )}
          {overallProgress === 100 && (
            <Button size="sm" variant="default" className="ml-auto">
              完成
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
