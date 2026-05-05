// 深度学习模型页面 - 模型选择、训练、对比
import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { Brain, Loader2, CheckCircle, BarChart3, Cpu, Layers, GitGraph, ArrowRightLeft } from "lucide-react"

const CATEGORY_ICONS: Record<string, any> = {
  "时序": BarChart3,
  "图神经网络": GitGraph,
  "注意力": Layers,
  "自适应": ArrowRightLeft,
  "域适应": Cpu,
}

export function DlModelsPage() {
  const [training, setTraining] = useState<string | null>(null)
  const [trainResult, setTrainResult] = useState<any>(null)

  const { data } = useQuery({
    queryKey: ["dl-models", "list"],
    queryFn: () => api.dlModels.list(),
    staleTime: 5 * 60 * 1000,
  })

  const handleTrain = async (modelId: string) => {
    setTraining(modelId)
    setTrainResult(null)
    try {
      const result = await api.dlModels.train(modelId)
      setTrainResult(result)
    } catch {
      setTrainResult({ error: "训练失败" })
    } finally {
      setTraining(null)
    }
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Brain className="h-8 w-8 text-slate-600" />
          深度学习
        </h1>
        <p className="text-muted-foreground">Qlib 内置深度学习模型训练与评估</p>
      </div>

      {/* 模型卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {(data?.models || []).map((m: any) => {
          const Icon = CATEGORY_ICONS[m.category] || Brain
          return (
            <Card key={m.id} className="hover:shadow-md transition-shadow">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Icon className="h-5 w-5 text-muted-foreground" />
                    <CardTitle className="text-base">{m.full_name}</CardTitle>
                  </div>
                  <Badge variant="outline" className="text-xs">{m.category}</Badge>
                </div>
                <CardDescription className="text-xs">{m.description}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">适用场景:</p>
                  <div className="flex flex-wrap gap-1">
                    {(m.best_for || []).map((s: string) => (
                      <Badge key={s} variant="secondary" className="text-xs">{s}</Badge>
                    ))}
                  </div>
                </div>
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">默认配置:</p>
                  <div className="grid grid-cols-2 gap-1">
                    {Object.entries(m.default_config || {}).slice(0, 4).map(([k, v]) => (
                      <div key={k} className="text-xs p-1 bg-muted/50 rounded flex justify-between">
                        <span className="text-muted-foreground">{k}</span>
                        <span className="font-mono">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <Button
                  onClick={() => handleTrain(m.id)}
                  disabled={training === m.id}
                  variant={m.is_trained ? "outline" : "default"}
                  className="w-full"
                  size="sm"
                >
                  {training === m.id ? (
                    <Loader2 className="h-3 w-3 animate-spin mr-1" />
                  ) : m.is_trained ? (
                    <CheckCircle className="h-3 w-3 mr-1" />
                  ) : null}
                  {m.is_trained ? "查看模型" : "开始训练"}
                </Button>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* 训练结果 */}
      {trainResult && !trainResult.error && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-emerald-500" />
              训练任务已创建
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex gap-4 text-sm">
                <span className="text-muted-foreground">Task ID:</span>
                <span className="font-mono">{trainResult.task_id}</span>
              </div>
              <div className="flex gap-4 text-sm">
                <span className="text-muted-foreground">模型:</span>
                <span>{trainResult.model}</span>
              </div>
              <p className="text-xs text-muted-foreground">{trainResult.message}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 说明 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">模型说明</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>• <strong>ALSTM:</strong> Attention LSTM，擅长捕捉时序模式，适合趋势预测和波动率建模</p>
          <p>• <strong>HIST:</strong> 基于图卷积的股票关系网络，利用行业和相关性建模</p>
          <p>• <strong>Transformer:</strong> 多头自注意力架构，自动发现特征交互和关键时间点</p>
          <p>• <strong>TRA:</strong> 市场状态自适应模型，降低牛熊切换时的策略失效风险</p>
          <p>• <strong>DDG-DA:</strong> 分布偏移域适应，减少训练/测试集分布差异的影响</p>
          <p className="text-xs mt-2">
            注: 完整训练需要 PyTorch + Qlib 完整依赖环境。当前版本提供模型配置预览和接口框架。
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
