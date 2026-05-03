// Skeleton 加载占位组件
import { cn } from "@/lib/utils"

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "text" | "circular" | "card"
}

export function Skeleton({ className, variant = "default", ...props }: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-muted",
        variant === "circular" && "rounded-full",
        variant === "text" && "h-4 w-full",
        variant === "card" && "h-24 w-full",
        className
      )}
      {...props}
    />
  )
}

// 卡片骨架
export function CardSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="p-6 border rounded-xl">
            <Skeleton className="h-4 w-24 mb-2" />
            <Skeleton className="h-8 w-16" />
          </div>
        ))}
      </div>
    </div>
  )
}

// 表格骨架
export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center space-x-4">
          <Skeleton className="h-12 w-12 rounded-full" />
          <div className="space-y-2 flex-1">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  )
}

// K线图骨架
export function ChartSkeleton({ height = 400 }: { height?: number }) {
  return (
    <div
      className="animate-pulse bg-muted rounded-lg flex items-center justify-center"
      style={{ height: `${height}px` }}
    >
      <div className="text-muted-foreground text-sm">加载图表数据...</div>
    </div>
  )
}

// 统计卡片骨架
export function MetricCardSkeleton() {
  return (
    <div className="p-6 border rounded-xl space-y-2">
      <Skeleton className="h-4 w-20" />
      <Skeleton className="h-8 w-16" />
      <Skeleton className="h-3 w-24" />
    </div>
  )
}
