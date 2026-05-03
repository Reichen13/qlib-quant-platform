// 直方图组件 - 用于因子分布分析
import { Bar, BarChart as RechartsBarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export interface HistogramProps {
  data: Array<{ bin: string; count: number }>
  title?: string
  description?: string
  height?: number
  color?: string
  showNormalCurve?: boolean
  mean?: number
  std?: number
}

export function Histogram({
  data,
  title,
  description,
  height = 250,
  color = "var(--color-primary)",
  showNormalCurve = false,
  mean,
  std,
}: HistogramProps) {
  // 计算正态分布曲线（如果需要）
  const normalCurveData = showNormalCurve && mean !== undefined && std !== undefined
    ? data.map((d) => {
        const x = parseFloat(d.bin.split("-")[0])
        const y = (1 / (std * Math.sqrt(2 * Math.PI))) *
                  Math.exp(-0.5 * Math.pow((x - mean) / std, 2))
        const maxCount = Math.max(...data.map((d) => d.count))
        const maxY = (1 / (std * Math.sqrt(2 * Math.PI)))
        return {
          ...d,
          normal: Math.round((y / maxY) * maxCount),
        }
      })
    : data

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
          <RechartsBarChart data={normalCurveData} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis
              dataKey="bin"
              stroke="var(--color-muted-foreground)"
              fontSize={12}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              stroke="var(--color-muted-foreground)"
              fontSize={12}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--color-card)",
                border: "1px solid var(--color-border)",
                borderRadius: "8px",
              }}
              labelStyle={{ color: "var(--color-foreground)" }}
              itemStyle={{ color: "var(--color-foreground)" }}
              formatter={(value) => [value, "因子数量"]}
            />
            <Bar
              dataKey="count"
              fill={color}
              radius={[4, 4, 0, 0]}
              opacity={0.8}
            />
          </RechartsBarChart>
        </ResponsiveContainer>
        {mean !== undefined && std !== undefined && (
          <div className="flex justify-center gap-6 mt-4 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">均值:</span>
              <span className="font-medium">{mean.toFixed(4)}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">标准差:</span>
              <span className="font-medium">{std.toFixed(4)}</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
