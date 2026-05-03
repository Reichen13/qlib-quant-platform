// 瀑布图组件 - 用于收益分解
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export interface WaterfallDataPoint {
  name: string
  value: number
  color?: string
  isTotal?: boolean
}

export interface WaterfallChartProps {
  data: WaterfallDataPoint[]
  height?: number
  title?: string
  description?: string
  valueFormat?: (value: number) => string
}

export function WaterfallChart({
  data,
  height = 300,
  title,
  description,
  valueFormat = (v) => v.toFixed(2),
}: WaterfallChartProps) {
  // 计算瀑布图的坐标
  let cumulative = 0
  const chartData = data.map((item) => {
    const value = item.value
    const start = cumulative
    const end = cumulative + value
    cumulative = end

    return {
      ...item,
      start,
      end,
      barHeight: Math.abs(value),
      y: value >= 0 ? start : end,
    }
  })

  const maxValue = Math.max(...chartData.map((d) => Math.max(d.start, d.end)))
  const minValue = Math.min(...chartData.map((d) => Math.min(d.start, d.end)))
  const range = maxValue - minValue || 1

  // 计算每个条形的位置和高度
  const barWidth = Math.max(30, (800 - 100) / data.length - 10)

  return (
    <Card>
      {(title || description) && (
        <CardHeader>
          {title && <CardTitle>{title}</CardTitle>}
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </CardHeader>
      )}
      <CardContent>
        <div className="w-full overflow-x-auto">
          <svg width="100%" height={height} viewBox={`0 0 ${Math.max(800, data.length * (barWidth + 10) + 100)} ${height}`}>
            {/* Y轴网格线 */}
            {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
              const y = height - 50 - (pct * (height - 80))
              return (
                <line
                  key={pct}
                  x1={60}
                  y1={y}
                  x2={Math.max(800, data.length * (barWidth + 10) + 80)}
                  y2={y}
                  stroke="var(--color-border)"
                  strokeDasharray="4 4"
                />
              )
            })}

            {/* Y轴标签 */}
            {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
              const value = minValue + pct * range
              const y = height - 50 - (pct * (height - 80))
              return (
                <text
                  key={pct}
                  x={50}
                  y={y + 4}
                  textAnchor="end"
                  fontSize="11"
                  fill="var(--color-muted-foreground)"
                >
                  {valueFormat(value)}
                </text>
              )
            })}

            {/* 条形 */}
            {chartData.map((d, i) => {
              const x = 70 + i * (barWidth + 10)
              const barYStart = height - 50 - ((d.start - minValue) / range) * (height - 80)
              const barYEnd = height - 50 - ((d.end - minValue) / range) * (height - 80)
              const barHeight = Math.abs(barYEnd - barYStart)
              const barY = Math.min(barYStart, barYEnd)

              const barColor = d.color || (d.value >= 0 ? "var(--color-up)" : "var(--color-down)")

              return (
                <g key={i}>
                  {/* 条形 */}
                  <rect
                    x={x}
                    y={barY}
                    width={barWidth}
                    height={barHeight}
                    fill={barColor}
                    opacity={d.isTotal ? 1 : 0.8}
                    rx={2}
                  />
                  {/* X轴标签 */}
                  <text
                    x={x + barWidth / 2}
                    y={height - 25}
                    textAnchor="middle"
                    fontSize="11"
                    fill="var(--color-foreground)"
                  >
                    {d.name}
                  </text>
                  {/* 数值标签 */}
                  <text
                    x={x + barWidth / 2}
                    y={barY - 5}
                    textAnchor="middle"
                    fontSize="11"
                    fontWeight="500"
                    fill={d.value >= 0 ? "var(--color-up)" : "var(--color-down)"}
                  >
                    {d.value >= 0 ? "+" : ""}{valueFormat(d.value)}
                  </text>
                </g>
              )
            })}

            {/* 零线 */}
            {minValue < 0 && maxValue > 0 && (
              <line
                x1={60}
                y1={height - 50 - ((0 - minValue) / range) * (height - 80)}
                x2={Math.max(800, data.length * (barWidth + 10) + 80)}
                y2={height - 50 - ((0 - minValue) / range) * (height - 80)}
                stroke="var(--color-muted-foreground)"
                strokeWidth="1"
              />
            )}
          </svg>
        </div>

        {/* 图例 */}
        <div className="flex justify-center gap-6 mt-4 text-sm">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded" style={{ backgroundColor: "var(--color-up)" }} />
            <span>正向收益</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded" style={{ backgroundColor: "var(--color-down)" }} />
            <span>负向收益</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
