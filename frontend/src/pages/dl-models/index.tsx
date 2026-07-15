// 深度学习模型页面 - 模型选择、训练、预测、信号
import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useAppStore } from "@/stores/app-store"
import { Brain, Loader2, CheckCircle, BarChart3, Cpu, Layers, GitGraph, ArrowRightLeft, TrendingUp, Zap } from "lucide-react"

const CATEGORY_ICONS: Record<string, any> = {
  "时序": BarChart3,
  "图神经网络": GitGraph,
  "注意力": Layers,
  "自u9002应": ArrowRightLeft,
  "域适应": Cpu,
}

export function DlModelsPage() {
  const { dlModelsParams, setDlModelsParams } = useAppStore()
  const { trainingModelId, trainingTaskId } = dlModelsParams
  const trainResult = dlModelsParams.trainResult as any
  const trainStatus = trainResult?.status

  const [predictTaskId, setPredictTaskId] = useState<string | null>(null)
  const [predictResult, setPredictResult] = useState<any>(null)
  const [predictingModel, setPredictingModel] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data } = useQuery({
    queryKey: ["dl-models", "list"],
    queryFn: () => api.dlModels.list(),
    staleTime: 5 * 60 * 1000,
  })

  const { data: signalData } = useQuery({
    queryKey: ["dl-models", "signal"],
    queryFn: () => api.dlModels.signal(10),
    staleTime: 60 * 1000,
  })

  const handleTrain = async (modelId: string) => {
    setDlModelsParams({ trainingModelId: modelId, trainingTaskId: null, trainResult: null })
    try {
      const result = await api.dlModels.train(modelId)
      setDlModelsParams({
        trainingModelId: result.status === "running" ? modelId : null,
        trainingTaskId: result.task_id || null,
        trainResult: result,
      })
    } catch {
      setDlModelsParams({ trainingModelId: null, trainingTaskId: null, trainResult: { error: "训练失败" } })
    }
  }

  const handlePredict = async (modelId: string) => {
    setPredictingModel(modelId)
    setPredictResult(null)
    try {
      const result = await api.dlModels.predict(modelId, 20)
      setPredictTaskId(result.task_id)
      setPredictResult(result)
    } catch (e: any) {
      setPredictResult({ status: "failed", message: e?.message || "预测启动失败" })
      setPredictingModel(null)
    }
  }

  useEffect(() => {
    if (!trainingTaskId || trainStatus !== "running") return
    const pollStatus = async () => {
      try {
        const result = await api.dlModels.status(trainingTaskId)
        setDlModelsParams({
          trainingModelId: result.status === "running" ? result.model || trainingModelId : null,
          trainingTaskId: result.status === "running" ? trainingTaskId : null,
          trainResult: result,
        })
        if (result.status !== "running") {
          queryClient.invalidateQueries({ queryKey: ["dl-models", "list"] })
        }
      } catch {
        setDlModelsParams({
          trainingModelId: null,
          trainingTaskId: null,
          trainResult: { ...trainResult, status: "failed", error: "无法查询训练任务状态" },
        })
      }
    }
    pollStatus()
    const interval = setInterval(pollStatus, 3000)
    return () => clearInterval(interval)
  }, [trainingModelId, trainingTaskId, trainStatus, setDlModelsParams, queryClient])

  useEffect(() => {
    if (!predictTaskId || predictResult?.status !== "running") return
    const poll = async () => {
      try {
        const result = await api.dlModels.predictStatus(predictTaskId)
        setPredictResult(result)
        if (result.status !== "running") {
          setPredictingModel(null)
          queryClient.invalidateQueries({ queryKey: ["dl-models", "signal"] })
        }
      } catch {
        setPredictResult({ status: "failed", message: "无法查询预测状态" })
        setPredictingModel(null)
      }
    }
    poll()
    const interval = setInterval(poll, 3000)
    return () => clearInterval(interval)
  }, [predictTaskId, predictResult, queryClient])

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Brain className="h-8 w-8 text-slate-600" />
          深度学习
        </h1>
        <p className="text-muted-foreground">Qlib 内置深度学习模型训练、预测与信号输出</p>
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
                <div className="flex gap-2">
                  <Button
                    onClick={() => handleTrain(m.id)}
                    disabled={trainingModelId === m.id}
                    variant={m.is_trained ? "outline" : "default"}
                    className="flex-1"
                    size="sm"
                  >
                    {trainingModelId === m.id ? (
                      <Loader2 className="h-3 w-3 animate-spin mr-1" />
                    ) : m.is_trained ? (
                      <CheckCircle className="h-3 w-3 mr-1" />
                    ) : null}
                    {m.is_trained ? "重u65b0训练" : "开始训练"}
                  </Button>
                  {m.is_trained && (
                    <Button
                      onClick={() => handlePredict(m.id)}
                      disabled={predictingModel === m.id}
                      variant="secondary"
                      size="sm"
                    >
                      {predictingModel === m.id ? (
                        <Loader2 className="h-3 w-3 animate-spin mr-1" />
                      ) : (
                        <Zap className="h-3 w-3 mr-1" />
                      )}
                      预测
                    </Button>
                  )}
                </div>
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
              {trainStatus === "completed" ? (
                <CheckCircle className="h-4 w-4 text-emerald-500" />
              ) : (
                <Loader2 className="h-4 w-4 animate-spin" />
              )}
              训练任务{trainStatus === "completed" ? "完成" : "运行中"}
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
              {trainResult.progress != null && (
                <div className="flex gap-4 text-sm">
                  <span className="text-muted-foreground">进度:</span>
                  <span>{Math.round((trainResult.progress || 0) * 100)}%</span>
                </div>
              )}
              <p className="text-xs text-muted-foreground">{trainResult.message}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 预测结果 */}
      {predictResult && !predictResult.error && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              {predictResult.status === "completed" ? (
                <TrendingUp className="h-4 w-4 text-emerald-500" />
              ) : predictResult.status === "failed" ? (
                <span className="text-destructive">预测失败</span>
              ) : (
                <Loader2 className="h-4 w-4 animate-spin" />
              )}
              DL 预测结果{predictResult.status === "completed" ? ` - ${predictResult.pred_date || ""}` : ""}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {predictResult.status === "completed" && predictResult.predictions ? (
              <div className="space-y-2">
                {predictResult.predictions.slice(0, 20).map((p: any, i: number) => (
                  <div key={p.code} className="flex items-center justify-between p-2 bg-muted/50 rounded text-sm">
                    <div className="flex items-center gap-3">
                      <span className="text-muted-foreground font-mono w-6">#{i + 1}</span>
                      <span className="font-mono">{p.code}</span>
                      <span>{p.name}</span>
                    </div>
                    <span className="font-mono font-bold text-emerald-600">{p.score}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{predictResult.message}</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* DL 信号汇总 */}
      {signalData && signalData.total > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-blue-500" />
              DL 信号汇总
            </CardTitle>
            <CardDescription>
              来自 {signalData.active_models?.length || 0} 个已训练模型的最新预测，按得分排序
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {signalData.signals?.slice(0, 15).map((s: any, i: number) => (
                <div key={`${s.model}-${s.code}`} className="flex items-center justify-between p-2 bg-muted/50 rounded text-sm">
                  <div className="flex items-center gap-3">
                    <span className="text-muted-foreground font-mono w-6">#{i + 1}</span>
                    <span className="font-mono">{s.code}</span>
                    <span>{s.name}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant="outline" className="text-xs">{s.model_name}</Badge>
                    <span className="font-mono font-bold text-emerald-600">{s.score}</span>
                  </div>
                </div>
              ))}
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
          <p>• <strong>ALSTM:</strong> Attention LSTM，擅长捕抓时序模式，适合趋u52bf预测和u6ce2u52a8率建u6a21</p>
          <p>• <strong>HIST:</strong> 基u4e8eu56feu5377u79ef的u80a1u7968u5173u7cfbu7f51u7edc，u5229u7528行u4e1au548cu76f8u5173u6027建u6a21</p>
          <p>• <strong>Transformer:</strong> 多u5934u81eau6ce8u610fu67b6u6784，u81eau52a8u53d1u73b0u7279u5f81u4ea4u4e92和u5173u952eu65f6u95f4u70b9</p>
          <p>• <strong>TRA:</strong> 市场u72b6u6001u81eau9002u5e94模u578b，u964du4f4eu725bu718au5207u6362u65f6u7684u7b56u7565失u6548风u9669</p>
          <p>• <strong>GRU:</strong> 门u63a7u5faau73afu5355u5143，u7ed3u6784u7b80u6d01u9ad8u6548，u9002u5408u4f5cu4e3au57fau7ebfu6a21u578b</p>
          <p className="text-xs mt-2">
            训练后点击“预测”获u53d6u6700u65b0股u7968u6392u540d。DL 信号会u81eau52a8u51fau73b0u5728首u9875聚u706b点中，u4e0eu56e0u5b50选u80a1互u4e3au8865u5145。
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
