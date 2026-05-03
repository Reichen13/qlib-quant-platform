// 热力图组件 - 用于 ETF 动量分析
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export interface HeatmapCell {
  row: string
  col: string
  value: number
  label?: string
}

export interface HeatmapProps {
  data: HeatmapCell[]
  rowLabels: string[]
  colLabels: string[]
  title?: string
  description?: string
  cellSize?: number
  valueFormat?: (value: number) => string
  colorScale?: "green-red" | "blue-yellow" | "purple"
}

export function Heatmap({
  data,
  rowLabels,
  colLabels,
  title,
  description,
  cellSize = 50,
  valueFormat = (v) => `${v.toFixed(1)}%`,
  colorScale = "green-red",
}: HeatmapProps) {
  // 获取数据范围
  const values = data.map((d) => d.value)
  const minValue = Math.min(...values)
  const maxValue = Math.max(...values)
  const range = maxValue - minValue || 1

  // 颜色映射函数
  const getColor = (value: number) => {
    const normalized = (value - minValue) / range
    if (colorScale === "green-red") {
      // 红色(涨)到绿色(跌)
      if (normalized > 0.5) {
        const intensity = Math.round((normalized - 0.5) * 2 * 255)
        return `rgba(239, ${68 + intensity}, 68, ${0.6 + normalized * 0.4})`
      } else {
        const intensity = Math.round((0.5 - normalized) * 2 * 255)
        return `rgba(34, ${197 - intensity}, 94, ${0.6 + (1 - normalized) * 0.4})`
      }
    } else if (colorScale === "blue-yellow") {
      // 蓝色到黄色
      if (normalized > 0.5) {
        return `rgba(234, 179, 8, ${0.6 + normalized * 0.4})`
      } else {
        return `rgba(59, 130, 246, ${0.6 + (1 - normalized) * 0.4})`
      }
    } else {
      // 紫色渐变
      return `oklch(0.5 0.2 280 / ${0.6 + normalized * 0.4})`
    }
  }

  // 创建数据矩阵
  const matrix = rowLabels.map((row) => {
    return colLabels.map((col) => {
      return data.find((d) => d.row === row && d.col === col) || {
        row,
        col,
        value: 0,
        label: "N/A",
      }
    })
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
        <div className="overflow-x-auto">
          <div style={{ minWidth: colLabels.length * cellSize + 100 }}>
            {/* 列标签 */}
            <div className="flex" style={{ paddingLeft: "100px" }}>
              {colLabels.map((col) => (
                <div
                  key={col}
                  className="text-xs text-muted-foreground text-center"
                  style={{ width: cellSize }}
                >
                  {col}
                </div>
              ))}
            </div>

            {/* 热力图网格 */}
            {matrix.map((row, rowIndex) => (
              <div key={rowLabels[rowIndex]} className="flex items-center">
                {/* 行标签 */}
                <div
                  className="text-xs font-medium text-foreground text-right pr-2"
                  style={{ width: "100px" }}
                >
                  {rowLabels[rowIndex]}
                </div>
                {/* 单元格 */}
                {row.map((cell, colIndex) => (
                  <div
                    key={colLabels[colIndex]}
                    className="relative flex items-center justify-center text-xs font-medium cursor-pointer hover:opacity-80 transition-opacity"
                    style={{
                      width: cellSize,
                      height: cellSize,
                      backgroundColor: getColor(cell.value),
                      color:
                        Math.abs(cell.value) > (maxValue - minValue) / 2 + minValue
                          ? "white"
                          : "var(--color-foreground)",
                      border: "1px solid var(--color-border)",
                    }}
                    title={`${cell.row} - ${cell.col}: ${valueFormat(cell.value)}`}
                  >
                    {valueFormat(cell.value)}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>

        {/* 图例 */}
        <div className="flex items-center justify-center gap-2 mt-4">
          <span className="text-xs text-muted-foreground">低</span>
          <div
            className="h-3 rounded"
            style={{
              width: "150px",
              background: `linear-gradient(to right, ${getColor(minValue)}, ${getColor(maxValue)})`,
            }}
          />
          <span className="text-xs text-muted-foreground">高</span>
        </div>
      </CardContent>
    </Card>
  )
}
