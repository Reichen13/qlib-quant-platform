// 智能股票池页面 - 三层漏斗创建与管理
import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { Layers, Plus, RefreshCw, Trash2, Loader2, Filter, Check, AlertCircle } from "lucide-react"
import { useAppStore } from "@/stores/app-store"

export function StockPoolPage() {
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState("")
  const [creating, setCreating] = useState(false)
  const stockPoolParams = useAppStore((s) => s.stockPoolParams)
  const setStockPoolParams = useAppStore((s) => s.setStockPoolParams)
  const { selectedPool } = stockPoolParams
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["stock-pool", "list"],
    queryFn: () => api.stockPool.list(),
    staleTime: 30 * 1000,
  })

  const { data: poolDetail } = useQuery({
    queryKey: ["stock-pool", "detail", selectedPool],
    queryFn: () => api.stockPool.get(selectedPool!),
    enabled: !!selectedPool,
    staleTime: 30 * 1000,
  })
  const hasFallbackConstituents = poolDetail?.latest_constituents?.some((c: any) => c.warning)

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    try {
      await api.stockPool.create({
        name: newName.trim(),
        layer1: {
          exclude_st: true,
          exclude_new_ipo_days: 180,
          min_market_cap: 15_000_000_000,
          exclude_negative_equity: true,
          exclude_suspended: true,
          exclude_chi_next_star: true,
        },
        layer2: {
          factors: {},
          icir_weighted: true,
          industry_neutralize: true,
          icir_window: 120,
        },
        layer3: {
          max_stocks: 30,
          max_sector_weight: 0.25,
          max_correlation: 0.7,
          position_method: "equal_weight",
        },
      })
      setNewName("")
      setShowCreate(false)
      queryClient.invalidateQueries({ queryKey: ["stock-pool"] })
    } catch { /* ignore */ }
    finally { setCreating(false) }
  }

  const handleRefresh = async (id: string) => {
    try {
      await api.stockPool.refresh(id)
      queryClient.invalidateQueries({ queryKey: ["stock-pool"] })
    } catch { /* ignore */ }
  }

  const handleDelete = async (id: string) => {
    try {
      await api.stockPool.delete(id)
      if (selectedPool === id) setStockPoolParams({ selectedPool: null })
      queryClient.invalidateQueries({ queryKey: ["stock-pool"] })
    } catch { /* ignore */ }
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Layers className="h-8 w-8 text-slate-600" />
          智能股票池
        </h1>
        <p className="text-muted-foreground">三层漏斗过滤：硬过滤 → 因子打分 → 组合约束</p>
      </div>

      {/* 操作栏 */}
      <div className="flex gap-2">
        <Button onClick={() => setShowCreate(!showCreate)}>
          <Plus className="h-4 w-4 mr-2" />
          新建股票池
        </Button>
      </div>

      {/* 创建表单 */}
      {showCreate && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex gap-2">
              <Input
                placeholder="股票池名称，如 沪深300低估值"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="max-w-sm"
              />
              <Button onClick={handleCreate} disabled={creating || !newName.trim()}>
                {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                <span className="ml-2">创建</span>
              </Button>
              <Button variant="outline" onClick={() => setShowCreate(false)}>取消</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 池列表 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* 新建入口卡片 */}
        {(!data?.pools || data.pools.length === 0) && !isLoading && (
          <Card className="border-dashed border-2 flex items-center justify-center min-h-[160px] cursor-pointer hover:bg-muted/30 transition-colors" onClick={() => setShowCreate(true)}>
            <div className="text-center space-y-2">
              <Layers className="h-8 w-8 mx-auto text-muted-foreground" />
              <p className="text-sm text-muted-foreground">暂无股票池，点击创建</p>
            </div>
          </Card>
        )}

        {(data?.pools || []).map((p: any) => (
          <Card
            key={p.id}
            className={`hover:shadow-md transition-shadow cursor-pointer ${selectedPool === p.id ? "ring-2 ring-primary" : ""}`}
            onClick={() => setStockPoolParams({ selectedPool: p.id })}
          >
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center justify-between">
                <span>{p.name}</span>
                <div className="flex gap-1">
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); handleRefresh(p.id) }}>
                    <RefreshCw className="h-3 w-3" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-red-500" onClick={(e) => { e.stopPropagation(); handleDelete(p.id) }}>
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </CardTitle>
              <CardDescription>
                更新于 {p.updated_at?.slice(0, 16) || "--"}
              </CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>

      {/* 池详情 */}
      {poolDetail && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Filter className="h-4 w-4" />
              {poolDetail.name} - 详情
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* 三层配置摘要 */}
            <div className="grid gap-3 md:grid-cols-3">
              <div className="p-3 bg-muted/30 rounded-lg">
                <h4 className="text-sm font-medium mb-2">Layer 1: 硬过滤</h4>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <p>排除ST: {poolDetail.config?.layer1?.exclude_st ? "是" : "否"}</p>
                  <p>新股过滤: {poolDetail.config?.layer1?.exclude_new_ipo_days || 180} 天</p>
                  <p>最小市值: {Math.round((poolDetail.config?.layer1?.min_market_cap || 0) / 1e8)} 亿</p>
                </div>
              </div>
              <div className="p-3 bg-muted/30 rounded-lg">
                <h4 className="text-sm font-medium mb-2">Layer 2: 因子打分</h4>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <p>ICIR加权: {poolDetail.config?.layer2?.icir_weighted ? "是" : "否"}</p>
                  <p>行业中性化: {poolDetail.config?.layer2?.industry_neutralize ? "是" : "否"}</p>
                  <p>ICIR窗口: {poolDetail.config?.layer2?.icir_window || 120} 日</p>
                </div>
              </div>
              <div className="p-3 bg-muted/30 rounded-lg">
                <h4 className="text-sm font-medium mb-2">Layer 3: 组合约束</h4>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <p>最大股票数: {poolDetail.config?.layer3?.max_stocks || 30}</p>
                  <p>行业上限: {((poolDetail.config?.layer3?.max_sector_weight || 0.25) * 100).toFixed(0)}%</p>
                  <p>相关性上限: {poolDetail.config?.layer3?.max_correlation || 0.7}</p>
                </div>
              </div>
            </div>

            {/* 最新成分 */}
            {poolDetail.latest_constituents?.length > 0 && (
              <div>
                <h4 className="text-sm font-medium mb-2">
                  最新成分 ({poolDetail.latest_constituents.length} 只, 更新于 {poolDetail.latest_refresh})
                </h4>
                {hasFallbackConstituents && (
                  <div className="mb-3 flex items-start gap-2 rounded-md border border-yellow-500/50 bg-yellow-500/10 p-3 text-sm text-yellow-700 dark:text-yellow-300">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>当前股票池使用降级打分结果，因子数据暂不可用；请先作为候选观察，不要按正式因子排名使用。</span>
                  </div>
                )}
                <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                  {poolDetail.latest_constituents.map((c: any, i: number) => (
                    <div key={i} className="p-2 bg-muted/30 rounded text-center">
                      <p className="text-xs font-mono">{c.code}</p>
                      {c.weight != null && (
                        <p className="text-xs text-muted-foreground">{(c.weight * 100).toFixed(1)}%</p>
                      )}
                      {c.warning && (
                        <p className="mt-1 text-[11px] text-yellow-700 dark:text-yellow-300">降级打分</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* 架构说明 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">三层漏斗架构</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>• <strong>Layer 1 — 硬过滤:</strong> 排除ST股、新股、资不抵债、停牌、科创板股票，设定最低市值门槛</p>
          <p>• <strong>Layer 2 — 因子打分:</strong> 基于已验证的Alpha因子，ICIR加权打分，可选行业中性化</p>
          <p>• <strong>Layer 3 — 组合约束:</strong> 控制股票数量、行业集中度、成对相关性，输出最终组合</p>
          <p className="text-xs mt-2">
            注: 股票范围来自 Baostock 全市场列表或本地 Qlib 行情目录；因子、行业等缺失时页面会显示提示，不生成示例成分。
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
