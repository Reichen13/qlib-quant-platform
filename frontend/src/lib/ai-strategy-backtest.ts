import type { BacktestParams } from "@/stores/app-store"

type GeneratedStrategyParams = Record<string, unknown>

function stringValue(value: unknown, fallback: string): string {
  if (value === undefined || value === null || value === "") {
    return fallback
  }
  return String(value)
}

function modelValue(value: unknown, fallback: string): string {
  const model = String(value || "").toLowerCase()
  if (model === "lightgbm" || model === "xgboost") {
    return model
  }
  return fallback
}

export function mapAiStrategyParamsToBacktestParams(
  params: GeneratedStrategyParams,
  current: BacktestParams,
): BacktestParams {
  return {
    ...current,
    model: modelValue(params.model, current.model),
    trainStart: stringValue(params.train_start, current.trainStart),
    trainEnd: stringValue(params.train_end, current.trainEnd),
    testStart: stringValue(params.test_start, current.testStart),
    testEnd: stringValue(params.test_end, current.testEnd),
    topK: stringValue(params.hold_num, current.topK),
    rebalance: stringValue(params.turnover, current.rebalance),
    commission: stringValue(params.buy_cost, current.commission),
    slippage: stringValue(params.sell_cost, current.slippage),
    singlePosition: stringValue(params.max_position, current.singlePosition),
    stopLoss: stringValue(params.stop_loss, current.stopLoss),
  }
}
