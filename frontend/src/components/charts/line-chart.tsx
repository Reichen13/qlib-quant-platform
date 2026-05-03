// 折线图组件 - 使用 Recharts
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"
import { cn } from "@/lib/utils"

interface LineChartProps {
  data: Array<Record<string, string | number>>
  lines: Array<{ dataKey: string; name: string; color?: string }>
  xKey: string
  height?: number
  className?: string
}

export function LineChartComponent({
  data,
  lines,
  xKey,
  height = 300,
  className,
}: LineChartProps) {
  const defaultColors = [
    "var(--color-primary)",
    "var(--color-up)",
    "var(--color-down)",
    "#f59e0b",
    "#8b5cf6",
  ]

  return (
    <div className={cn("w-full", className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey={xKey}
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
              backgroundColor: "var(--color-popover)",
              border: "1px solid var(--color-border)",
              borderRadius: "6px",
            }}
            labelStyle={{ color: "var(--color-foreground)" }}
          />
          <Legend />
          {lines.map((line, index) => (
            <Line
              key={line.dataKey}
              type="monotone"
              dataKey={line.dataKey}
              name={line.name}
              stroke={line.color || defaultColors[index % defaultColors.length]}
              strokeWidth={2}
              dot={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
