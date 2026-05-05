// 宏观策略仪表板 - Bridgewater 风格宏观分析
import { useMemo } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useQuery } from "@tanstack/react-query"
import { Globe, Activity, Loader2 } from "lucide-react"
import { api } from "@/lib/api"
import { LineChartComponent } from "@/components/charts/line-chart"
import { InstructionsPanel } from "@/components/features/instructions-panel"

// 四象限图参数
const QUADRANT_CONFIG = {
  width: 280,
  height: 280,
  padding: 40,
  centerX: 140,
  centerY: 140,
  radius: 100,
}

function QuadrantChart({ growthScore, inflationScore, regimeLabel }: {
  growthScore: number
  inflationScore: number
  regimeLabel: string
}) {
  const { width, height, padding, centerX, centerY, radius } = QUADRANT_CONFIG
  // 坐标转换: score 范围 [-2, 2] -> pixel
  const x = centerX + (growthScore / 2) * radius
  const y = centerY - (inflationScore / 2) * radius

  // 象限颜色
  const getQuadrantColor = (gx: number, iy: number) => {
    if (gx > 0 && iy < 0) return "rgba(38,166,154,0.15)" // 复苏 - 最佳
    if (gx > 0 && iy > 0) return "rgba(245,166,35,0.12)" // 过热 - 注意
    if (gx < 0 && iy < 0) return "rgba(74,144,226,0.12)" // 通缩 - 中性
    return "rgba(239,83,80,0.12)" // 滞胀 - 风险
  }

  return (
    <div className="flex flex-col items-center">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {/* 背景象限 */}
        <rect x={padding} y={padding} width={centerX - padding} height={centerY - padding} fill={getQuadrantColor(-1, 1)} />
        <rect x={centerX} y={padding} width={centerX - padding} height={centerY - padding} fill={getQuadrantColor(1, 1)} />
        <rect x={padding} y={centerY} width={centerX - padding} height={centerY - padding} fill={getQuadrantColor(-1, -1)} />
        <rect x={centerX} y={centerY} width={centerX - padding} height={centerY - padding} fill={getQuadrantColor(1, -1)} />

        {/* 象限标签 */}
        <text x={padding + 10} y={centerY - 10} fontSize="11" fill="var(--muted-foreground)" opacity={0.7}>
          通缩期
        </text>
        <text x={centerX + 10} y={centerY - 10} fontSize="11" fill="var(--muted-foreground)" opacity={0.7}>
          复苏期
        </text>
        <text x={padding + 10} y={height - padding + 10} fontSize="11" fill="var(--muted-foreground)" opacity={0.7}>
          滞胀期
        </text>
        <text x={centerX + 10} y={height - padding + 10} fontSize="11" fill="var(--muted-foreground)" opacity={0.7}>
          过热期
        </text>

        {/* 坐标轴 */}
        <line x1={padding} y1={centerY} x2={width - padding} y2={centerY} stroke="var(--border)" strokeWidth={1} />
        <line x1={centerX} y1={padding} x2={centerX} y2={height - padding} stroke="var(--border)" strokeWidth={1} />

        {/* 轴标签 */}
        <text x={width - padding + 5} y={centerY + 4} fontSize="10" fill="var(--muted-foreground)">
          增长 →
        </text>
        <text x={centerX + 5} y={padding - 5} fontSize="10" fill="var(--muted-foreground)">
          ↑ 通胀
        </text>

        {/* 原点 */}
        <circle cx={centerX} cy={centerY} r={3} fill="var(--muted-foreground)" />

        {/* 当前位置 */}
        <circle cx={x} cy={y} r={8} fill="var(--color-primary)" opacity={0.8} />
        <circle cx={x} cy={y} r={4} fill="var(--color-primary)" />
        <text x={x + 12} y={y - 8} fontSize="12" fontWeight="bold" fill="var(--foreground)">
          {regimeLabel}
        </text>
      </svg>
    </div>
  )
}

function getTrendBadge(changePct: number) {
  if (changePct > 0) return <Badge variant="default" className="text-xs">上涨</Badge>
  if (changePct < 0) return <Badge variant="destructive" className="text-xs">下跌</Badge>
  return <Badge variant="outline" className="text-xs">持平</Badge>
}

function getRegimeColor(regime: string) {
  switch (regime) {
    case "recovery": return "var(--color-up)"
    case "overheat": return "#f5a623"
    case "deflation": return "#4a90d9"
    case "stagflation": return "var(--color-down)"
    default: return "var(--muted-foreground)"
  }
}

function getRegimeBadge(regime: string, label: string) {
  const colors: Record<string, string> = {
    recovery: "bg-up text-white",
    overheat: "bg-yellow-600 text-white",
    deflation: "bg-blue-600 text-white",
    stagflation: "bg-down text-white",
  }
  return <Badge className={colors[regime] || ""}>{label}</Badge>
}

export function MacroDashboardPage() {
  const { data: indicatorsData } = useQuery({
    queryKey: ["macro", "indicators"],
    queryFn: () => api.macro.indicators(),
    refetchInterval: 5 * 60 * 1000, // 5分钟刷新
  })

  const { data: regimeData, isLoading: regimeLoading } = useQuery({
    queryKey: ["macro", "regime"],
    queryFn: () => api.macro.regime({}),
    enabled: !!indicatorsData,
  })

  const { data: allocationData, isLoading: allocLoading } = useQuery({
    queryKey: ["macro", "allocation"],
    queryFn: () => api.macro.allocation({}),
    enabled: !!regimeData,
  })

  const { data: historyData } = useQuery({
    queryKey: ["macro", "history"],
    queryFn: () => api.macro.history(12),
  })

  // 兼容新旧 API 格式: 新格式有 china_indicators/us_indicators, 旧格式有 indicators
  const hasNewFormat = !!(indicatorsData?.china_indicators || indicatorsData?.us_indicators)
  const cnIndicators = indicatorsData?.china_indicators || []
  const usIndicators = indicatorsData?.us_indicators || (hasNewFormat ? [] : (indicatorsData?.indicators || []))
  const cnDerived = indicatorsData?.china_derived || {}
  const usDerived = indicatorsData?.us_derived || (hasNewFormat ? {} : (indicatorsData?.derived || {}))
  const regime = regimeData
  const allocation = allocationData?.allocation || []

  // 配置权重条数据
  const historyChartData = useMemo(() => {
    if (!historyData?.history) return []
    return historyData.history.map((h: any) => ({
      date: h.date,
      增长得分: h.growth_score,
      通胀得分: h.inflation_score,
    }))
  }, [historyData])

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* 页面标题 */}
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Globe className="h-8 w-8 text-blue-600" />
          宏观策略
        </h1>
        <p className="text-muted-foreground">Bridgewater 风格宏观仪表板 - 市场状态分类与全天候配置</p>
      </div>

      {/* 中国宏观指标 */}
      {cnIndicators.length > 0 && (
        <>
          <h3 className="text-sm font-medium text-muted-foreground mt-2">中国宏观指标</h3>
          <div className="grid gap-4 md:grid-cols-5">
            {cnIndicators.map((ind: any) => (
              <Card key={ind.name}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center justify-between">
                    {ind.name}
                    {getTrendBadge(ind.change_pct)}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {ind.name.includes("SHIBOR") || ind.name.includes("收益率") || ind.name.includes("PMI")
                      ? ind.value.toFixed(3)
                      : ind.value > 1000
                      ? ind.value.toFixed(0)
                      : ind.value.toFixed(2)}
                    {(ind.name.includes("SHIBOR") || ind.name.includes("收益率") || ind.name.includes("M2")) && "%"}
                    {ind.name === "北向资金净流入" && "亿"}
                  </div>
                  <p className={`text-xs ${ind.change_pct >= 0 ? "text-up" : "text-down"}`}>
                    {ind.change_pct >= 0 ? "+" : ""}{ind.change_pct.toFixed(1)}%
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}

      {/* 中国衍生指标 */}
      {Object.keys(cnDerived).length > 0 && (
        <div className="flex gap-2 flex-wrap mt-2">
          {cnDerived.pmi_level && (
            <Badge variant={cnDerived.pmi_level === "扩张" ? "default" : "secondary"}>
              PMI: {cnDerived.pmi_level}
            </Badge>
          )}
          {cnDerived.liquidity && (
            <Badge variant={cnDerived.liquidity === "宽松" ? "default" : "outline"}>
              流动性: {cnDerived.liquidity}
            </Badge>
          )}
          {cnDerived.north_flow_trend && (
            <Badge variant={cnDerived.north_flow_trend === "持续流入" ? "default" : "destructive"}>
              北向资金: {cnDerived.north_flow_trend}
            </Badge>
          )}
        </div>
      )}

      {/* 美国宏观指标 */}
      {usIndicators.length > 0 && (
        <>
          <h3 className="text-sm font-medium text-muted-foreground mt-4">美国宏观指标</h3>
          <div className="grid gap-4 md:grid-cols-5">
            {usIndicators.slice(0, 5).map((ind: any) => (
              <Card key={ind.name}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center justify-between">
                    {ind.name}
                    {getTrendBadge(ind.change_pct)}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {ind.name === "10年美债收益率" || ind.name === "波动率指数"
                      ? ind.value.toFixed(2)
                      : ind.value > 1000
                      ? ind.value.toFixed(0)
                      : ind.value.toFixed(2)}
                    {ind.name === "10年美债收益率" && "%"}
                  </div>
                  <p className={`text-xs ${ind.change_pct >= 0 ? "text-up" : "text-down"}`}>
                    近20日: {ind.change_pct >= 0 ? "+" : ""}{ind.change_pct.toFixed(1)}%
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}

      {/* 美国衍生指标 */}
      {Object.keys(usDerived).length > 0 && (
        <div className="flex gap-2 flex-wrap mt-2">
          {usDerived.fear_level && (
            <Badge variant={usDerived.fear_level === "恐慌" ? "destructive" : usDerived.fear_level === "担忧" ? "secondary" : "default"}>
              恐惧指数: {usDerived.fear_level}
            </Badge>
          )}
          {usDerived.yield_level && (
            <Badge variant="outline">
              利率水平: {usDerived.yield_level}
            </Badge>
          )}
          {usDerived.risk_on_ratio && (
            <Badge variant="outline">
              股/金比: {usDerived.risk_on_ratio}
            </Badge>
          )}
        </div>
      )}

      {/* 状态分类 + 配置建议 */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* 四象限图 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              市场状态分类
            </CardTitle>
            <CardDescription>增长 vs 通胀/风险 2x2 矩阵</CardDescription>
          </CardHeader>
          <CardContent>
            {regimeLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : regime ? (
              <div className="space-y-4">
                <QuadrantChart
                  growthScore={regime.growth_score}
                  inflationScore={regime.inflation_score}
                  regimeLabel={regime.regime_label}
                />
                <div className="flex items-center justify-center gap-4 pt-2">
                  {getRegimeBadge(regime.regime, regime.regime_label)}
                  <span className="text-sm text-muted-foreground">
                    增长得分: {regime.growth_score} | 通胀得分: {regime.inflation_score}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    置信度: {(regime.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">暂无状态数据</div>
            )}
          </CardContent>
        </Card>

        {/* 配置建议 */}
        <Card>
          <CardHeader>
            <CardTitle>全天候配置建议</CardTitle>
            <CardDescription>
              {regime ? `${regime.regime_label} - ${allocationData?.risk_level || "中性"}型配置` : "基于当前市场状态的资产配置"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {allocLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : allocation.length > 0 ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  {allocation.map((a: any) => (
                    <div key={a.asset} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium">{a.asset}</span>
                        <span className="text-muted-foreground">{(a.weight * 100).toFixed(0)}%</span>
                      </div>
                      <div className="h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${a.weight * 100}%`,
                            backgroundColor: getRegimeColor(regime?.regime || ""),
                          }}
                        />
                      </div>
                      <p className="text-xs text-muted-foreground">{a.reason}</p>
                    </div>
                  ))}
                </div>
                {allocationData?.summary && (
                  <div className="p-3 bg-muted rounded-lg text-sm">
                    <p className="font-medium mb-1">配置总结</p>
                    <p className="text-muted-foreground">{allocationData.summary}</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">暂无配置数据</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 历史状态演变 */}
      <Card>
        <CardHeader>
          <CardTitle>历史状态演变</CardTitle>
          <CardDescription>过去 12 个月的增长和通胀得分变化</CardDescription>
        </CardHeader>
        <CardContent>
          {historyChartData.length > 0 ? (
            <div className="space-y-4">
              <LineChartComponent
                data={historyChartData}
                lines={[
                  { dataKey: "增长得分", name: "增长得分", color: "var(--color-up)" },
                  { dataKey: "通胀得分", name: "通胀得分", color: "var(--color-down)" },
                ]}
                xKey="date"
                height={300}
              />
              {/* 状态标签行 */}
              <div className="flex flex-wrap gap-1">
                {historyData?.history?.map((h: any) => (
                  <Badge
                    key={h.date}
                    variant="outline"
                    className="text-xs"
                    style={{ borderColor: getRegimeColor(h.regime), color: getRegimeColor(h.regime) }}
                  >
                    {h.date.slice(0, 7)}
                  </Badge>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">暂无历史数据</div>
          )}
        </CardContent>
      </Card>

      {/* 全部指标详情 */}
      <Card>
        <CardHeader>
          <CardTitle>指标总览</CardTitle>
          <CardDescription>所有宏观指标详细数据</CardDescription>
        </CardHeader>
        <CardContent>
          {cnIndicators.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-4">
              {cnIndicators.map((ind: any) => (
                <div key={ind.name} className="p-3 bg-muted/50 rounded-lg space-y-1">
                  <p className="text-sm font-medium">{ind.name}</p>
                  <p className="text-xl font-bold">{ind.value.toFixed(2)}</p>
                  <div className="flex items-center gap-2">
                    {getTrendBadge(ind.change_pct)}
                    <span className={`text-xs ${ind.change_pct >= 0 ? "text-up" : "text-down"}`}>
                      20日: {ind.change_pct >= 0 ? "+" : ""}{ind.change_pct}%
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">Z-Score: {ind.z_score}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">暂无指标数据</div>
          )}
        </CardContent>
      </Card>

      {/* 策略说明 */}
      <InstructionsPanel
        title="宏观策略说明"
        description="Bridgewater 全天候策略框架 - 基于市场状态的资产配置"
        icon="info"
        defaultExpanded={false}
        instructions={[
          {
            title: "四象限状态分类",
            description: "基于增长和通胀两个维度将市场分为四个状态：复苏期（高增长低通胀）→ 增持股票/信用债；过热期（高增长高通胀）→ 增持商品/TIPS/黄金；通缩期（低增长低通胀）→ 增持国债/现金；滞胀期（低增长高通胀）→ 增持黄金/现金",
          },
          {
            title: "宏观指标",
            description: "使用 yfinance 实时获取 VIX（恐慌指数）、标普500、纳斯达克、10年美债收益率、黄金、原油、美元指数等关键宏观指标",
          },
          {
            title: "增长得分",
            description: "综合标普500、纳斯达克和罗素2000的20日涨跌幅和年度Z-Score计算，反映经济增长动能",
          },
          {
            title: "通胀/风险得分",
            description: "综合VIX水平、原油和黄金的价格变动，反映通胀压力和市场风险水平",
          },
          {
            title: "全天候配置",
            description: "参考 Bridgewater All-Weather 框架，根据不同状态自动调整资产配置权重。无论何种状态都不配置超过35%的单一资产，确保充分分散",
          },
        ]}
      />
    </div>
  )
}
