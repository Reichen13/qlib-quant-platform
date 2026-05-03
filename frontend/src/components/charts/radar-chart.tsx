// 雷达图组件 - 用于 ETF 多维度评分对比
import { Radar, RadarChart as RechartsRadarChart, ResponsiveContainer } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Legend, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Tooltip } from "recharts"

export interface RadarSeries {
  name: string
  data: Record<string, number>
  color: string
}

export interface RadarChartProps {
  series: RadarSeries[]
  dimensions: string[]
  height?: number
  title?: string
  description?: string
  maxValue?: number
}

export function RadarChart({
  series,
  dimensions,
  height = 350,
  title,
  description,
  maxValue = 100,
}: RadarChartProps) {
  // 转换数据为 Recharts 格式
  const chartData = dimensions.map((dim) => {
    const item: Record<string, string | number> = { dimension: dim }
    series.forEach((s) => {
      item[s.name] = s.data[dim] ?? 0
    })
    return item
  })

  return (
    <Card>
      {(title || description) && (
        <CardHeader>
          {title && <CardTitle>{title}</CardTitle>}
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </CardHeader>
      )}
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          <RechartsRadarChart data={chartData} margin={{ top: 20, right: 80, bottom: 20, left: 80 }}>
            <PolarGrid stroke="var(--color-border)" strokeWidth={1} />
            <PolarAngleAxis
              dataKey="dimension"
              tick={{ fill: "var(--color-foreground)", fontSize: 12 }}
            />
            <PolarRadiusAxis
              angle={90}
              domain={[0, maxValue]}
              tick={{ fill: "var(--color-muted-foreground)", fontSize: 10 }}
              tickCount={5}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--color-card)",
                border: "1px solid var(--color-border)",
                borderRadius: "8px",
              }}
              labelStyle={{ color: "var(--color-foreground)" }}
              itemStyle={{ color: "var(--color-foreground)" }}
            />
            <Legend
              wrapperStyle={{ paddingTop: "10px" }}
              iconType="circle"
            />
            {series.map((s) => (
              <Radar
                key={s.name}
                name={s.name}
                dataKey={s.name}
                stroke={s.color}
                fill={s.color}
                fillOpacity={0.3}
                strokeWidth={2}
              />
            ))}
          </RechartsRadarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
