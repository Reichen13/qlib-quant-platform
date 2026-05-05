import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// 格式化数字
export function formatNumber(num: number, decimals: number = 2): string {
  return num.toFixed(decimals)
}

// 格式化百分比
export function formatPercent(num: number, decimals: number = 2): string {
  const signed = num > 0 ? "+" : ""
  return signed + num.toFixed(decimals) + "%"
}

// 格式化股票代码
export function formatStockCode(code: string): string {
  return code
}

// 判断涨跌
export function getPriceChangeClass(change: number): string {
  return change > 0 ? "text-up" : change < 0 ? "text-down" : ""
}

// 获取透明度颜色
export function getTransparencyColor(level: string): string {
  switch (level) {
    case "HIGH":
      return "text-blue-600"
    case "MEDIUM":
      return "text-yellow-600"
    case "LOW":
      return "text-red-600"
    default:
      return "text-gray-600"
  }
}

// 获取透明度标签
export function getTransparencyLabel(level: string): string {
  switch (level) {
    case "HIGH":
      return "高透明度"
    case "MEDIUM":
      return "中透明度"
    case "LOW":
      return "低透明度"
    default:
      return "未知"
  }
}

// 格式化日期
export function formatDate(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date
  return d.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  })
}

/** 将 Date 转为 YYYY-MM-DD 字符串 */
export function toDateString(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const day = String(d.getDate()).padStart(2, "0")
  return `${y}-${m}-${day}`
}

/** 相对 today 偏移的日期字符串 */
export function relativeDate(offsets: { years?: number; months?: number; days?: number }): string {
  const d = new Date()
  if (offsets.years) d.setFullYear(d.getFullYear() + offsets.years)
  if (offsets.months) d.setMonth(d.getMonth() + offsets.months)
  if (offsets.days) d.setDate(d.getDate() + offsets.days)
  return toDateString(d)
}
