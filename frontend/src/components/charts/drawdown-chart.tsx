// 回撤图组件 - 显示策略回撤情况
import { Area, AreaChart as RechartsAreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export interface DrawdownDataPoint {
  date: string
  value: number
}

export interface DrawdownChartProps {
  data: DrawdownDataPoint[]
  height?: number
  title?: string
  description?: string
}

export function DrawdownChart({
  data,
  height = 250,
  title,
  description,
}: DrawdownChartProps) {
  // 找到最大回撤
  const maxDrawdown = Math.min(...data.map((d) => d.value))

  return (
    <Card>
      {(title || description) && (
        <CardHeader>
          <div className="flex items-center justify-between">
            {title && <CardTitle>{title}</CardTitle>}
            {description && <p className="text-sm text-muted-foreground">{description}</p>}
          </div>
        </CardHeader>
      )}
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          <RechartsAreaChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-down)" stopOpacity={0.6} />
                <stop offset="100%" stopColor="var(--color-down)" stopOpacity={0.1} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis
              dataKey="date"
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
              tickFormatter={(value) => `${value.toFixed(1)}%`}
              domain={[Math.min(-50, maxDrawdown * 1.1), 0]}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--color-card)",
                border: "1px solid var(--color-border)",
                borderRadius: "8px",
              }}
              labelStyle={{ color: "var(--color-foreground)" }}
              itemStyle={{ color: "var(--color-down)" }}
              formatter={(value) => [`${Number(value).toFixed(2)}%`, "回撤"]}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="var(--color-down)"
              strokeWidth={2}
              fill="url(#drawdownGradient)"
            />
          </RechartsAreaChart>
        </ResponsiveContainer>
        <div className="flex justify-between mt-4 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">最大回撤:</span>
            <span className="font-medium text-down">{maxDrawdown.toFixed(2)}%</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">回撤天数:</span>
            <span className="font-medium">{data.filter((d) => d.value < -5).length} 天</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
