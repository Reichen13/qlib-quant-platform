// 操作建议组件 - 显示回测后的交易建议
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { TrendingUp, TrendingDown, AlertCircle, CheckCircle } from "lucide-react"

export interface StockAdvice {
  code: string
  name: string
  score: number
  reason: string
  currentPrice?: number
  targetPrice?: number
}

export interface OperationAdviceProps {
  topBuys: StockAdvice[]
  topSells: StockAdvice[]
  positionAdvice: string
  riskLevel: "low" | "medium" | "high"
  lastUpdate: string
}

export function OperationAdvice({
  topBuys,
  topSells,
  positionAdvice,
  riskLevel,
  lastUpdate,
}: OperationAdviceProps) {
  const getRiskBadge = () => {
    switch (riskLevel) {
      case "low":
        return <Badge variant="default">低风险</Badge>
      case "medium":
        return <Badge className="bg-yellow-600">中等风险</Badge>
      case "high":
        return <Badge variant="destructive">高风险</Badge>
    }
  }

  return (
    <div className="space-y-4">
      {/* 仓位建议 */}
      <Card className="border-up/50 bg-up/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle className="h-5 w-5 text-up" />
            仓位建议
          </CardTitle>
          <CardDescription>基于当前市场信号的综合建议</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-2xl font-bold">{positionAdvice}</p>
              <p className="text-sm text-muted-foreground mt-1">
                建议仓位: 根据市场趋势调整
              </p>
            </div>
            {getRiskBadge()}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <AlertCircle className="h-4 w-4" />
            <span>更新时间: {lastUpdate}</span>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {/* 买入建议 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-up" />
              建议买入
              <Badge variant="default">{topBuys.length}</Badge>
            </CardTitle>
            <CardDescription>Top K 筛选结果</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {topBuys.map((stock) => (
                <div
                  key={stock.code}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{stock.name}</span>
                      <Badge variant="outline">{stock.code}</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">{stock.reason}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold text-up">{stock.score}</div>
                    <div className="text-xs text-muted-foreground">评分</div>
                  </div>
                </div>
              ))}
              {topBuys.length === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                  暂无买入建议
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* 卖出建议 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingDown className="h-5 w-5 text-down" />
              建议卖出
              <Badge variant="destructive">{topSells.length}</Badge>
            </CardTitle>
            <CardDescription>风险控制建议</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {topSells.map((stock) => (
                <div
                  key={stock.code}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{stock.name}</span>
                      <Badge variant="outline">{stock.code}</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">{stock.reason}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold text-down">{stock.score}</div>
                    <div className="text-xs text-muted-foreground">评分</div>
                  </div>
                </div>
              ))}
              {topSells.length === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                  暂无卖出建议
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 操作说明 */}
      <Card>
        <CardHeader>
          <CardTitle>操作说明</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>• <strong>买入建议:</strong> 综合因子评分最高的股票，建议分批建仓</p>
          <p>• <strong>卖出建议:</strong> 评分下降或触发止损的股票，建议及时减仓</p>
          <p>• <strong>仓位控制:</strong> 根据市场趋势信号动态调整，高风险时降低仓位</p>
          <p>• <strong>风险提示:</strong> 历史回测结果不代表未来表现，请结合实际情况判断</p>
        </CardContent>
      </Card>
    </div>
  )
}
