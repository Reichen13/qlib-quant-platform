// 柱状图组件 - 使用 Recharts
import { Bar, BarChart as RechartsBarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export interface BarChartLine {
  dataKey: string
  name: string
  color: string
}

export interface BarChartProps {
  data: Array<Record<string, string | number>>
  bars: BarChartLine[]
  xKey: string
  height?: number
  title?: string
  description?: string
  layout?: "vertical" | "horizontal"
  showGrid?: boolean
  showLegend?: boolean
}

export function BarChart({
  data,
  bars,
  xKey,
  height = 300,
  title,
  description,
  layout = "vertical",
  showGrid = true,
  showLegend = true,
}: BarChartProps) {
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
          <RechartsBarChart
            data={data}
            layout={layout === "horizontal" ? "vertical" : "horizontal"}
            margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
          >
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />}
            <XAxis
              dataKey={xKey}
              stroke="var(--color-muted-foreground)"
              fontSize={12}
              tickLine={false}
              axisLine={false}
              angle={-45}
              textAnchor="end"
              height={80}
            />
            <YAxis
              stroke="var(--color-muted-foreground)"
              fontSize={12}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => value.toFixed(2)}
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
            {showLegend && (
              <Legend
                wrapperStyle={{ paddingTop: "20px" }}
                iconType="circle"
              />
            )}
            {bars.map((bar) => (
              <Bar
                key={bar.dataKey}
                dataKey={bar.dataKey}
                name={bar.name}
                fill={bar.color}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </RechartsBarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
