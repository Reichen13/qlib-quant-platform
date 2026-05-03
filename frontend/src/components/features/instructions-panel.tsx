// 使用说明展开面板组件 - 用于显示详细说明和帮助信息
import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { ChevronDown, ChevronRight, Info, AlertCircle } from "lucide-react"

export interface InstructionItem {
  title: string
  description: string
  code?: string
}

export interface InstructionsPanelProps {
  title?: string
  description?: string
  instructions: InstructionItem[]
  icon?: "info" | "warning" | "none"
  defaultExpanded?: boolean
  variant?: "default" | "compact"
}

export function InstructionsPanel({
  title = "使用说明",
  description,
  instructions,
  icon = "info",
  defaultExpanded = false,
  variant = "default",
}: InstructionsPanelProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)

  const getIcon = () => {
    switch (icon) {
      case "info":
        return <Info className="h-5 w-5 text-blue-600" />
      case "warning":
        return <AlertCircle className="h-5 w-5 text-yellow-600" />
      default:
        return null
    }
  }

  return (
    <Card className={variant === "compact" ? "" : "border-dashed"}>
      <CardHeader className={variant === "compact" ? "pb-2" : ""}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {getIcon()}
            <div>
              {title && <CardTitle className={variant === "compact" ? "text-base" : ""}>{title}</CardTitle>}
              {description && <CardDescription>{description}</CardDescription>}
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            {isExpanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </Button>
        </div>
      </CardHeader>
      {isExpanded && (
        <CardContent>
          <div className="space-y-3">
            {instructions.map((item, index) => (
              <div key={index} className="space-y-1">
                <p className="font-medium text-sm">{item.title}</p>
                <p className="text-sm text-muted-foreground">{item.description}</p>
                {item.code && (
                  <code className="block text-xs bg-muted px-2 py-1 rounded mt-1">
                    {item.code}
                  </code>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  )
}

// 预定义的使用说明
export const commonInstructions = {
  rsi: [
    { title: "RSI 指标", description: "相对强弱指数，用于衡量股票超买超卖程度" },
    { title: "超买信号", description: "RSI > 70，表示股票可能被过度买入，价格可能回调" },
    { title: "超卖信号", description: "RSI < 30，表示股票可能被过度卖出，价格可能反弹" },
  ],
  macd: [
    { title: "MACD 指标", description: "移动平均收敛散度，用于判断趋势转折点" },
    { title: "金叉买入", description: "DIF 上穿 DEA，且柱状图由负转正，买入信号" },
    { title: "死叉卖出", description: "DIF 下穿 DEA，且柱状图由正转负，卖出信号" },
  ],
  bollinger: [
    { title: "布林带", description: "基于移动平均线和标准差的技术指标" },
    { title: "突破上轨", description: "价格突破上轨，可能回调，考虑减仓" },
    { title: "跌破下轨", description: "价格跌破下轨，可能反弹，考虑建仓" },
  ],
  pairTrading: [
    { title: "配对选择", description: "选择具有长期协整关系的股票对（同行业、业务相似）" },
    { title: "协整检验", description: "通过统计检验验证两只股票价格是否存在长期均衡关系" },
    { title: "Z-Score", description: "价差的标准化分数，|Z| > 2 时出现交易机会" },
    { title: "做多价差", description: "Z > 2，价差过大，买入被低估股票，做空被高估股票" },
    { title: "做空价差", description: "Z < -2，价差过小，与做多相反" },
  ],
  etfRotation: [
    { title: "评分体系", description: "趋势得分 70% + RSI修正 30%" },
    { title: "趋势得分", description: "综合均线、MACD、动量等趋势指标" },
    { title: "RSI修正", description: "根据超买超卖程度调整评分" },
    { title: "强烈买入", description: "评分 >= 90，多指标共振向上" },
    { title: "买入", description: "评分 80-89，趋势向上" },
    { title: "持有", description: "评分 60-79，震荡整理" },
    { title: "规避", description: "评分 < 60，趋势向下" },
  ],
  backtest: [
    { title: "模型选择", description: "支持 LightGBM、XGBoost 等机器学习模型" },
    { title: "训练参数", description: "设置训练起止日期，建议至少 1 年数据" },
    { title: "Top K 策略", description: "每期选择因子评分最高的 K 只股票" },
    { title: "调仓周期", description: "每隔 N 天调仓一次，常用 20 日" },
    { title: "交易成本", description: "设置佣金率和滑点，影响回测准确性" },
    { title: "夏普比率", description: "年化收益 / 波动率，越大越好，>1 为优秀" },
    { title: "最大回撤", description: "从峰值到谷底的最大跌幅，越小越好" },
  ],
}
