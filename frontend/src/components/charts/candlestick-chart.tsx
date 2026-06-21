// K 线图组件 - 支持 MA、BOLL、成交量叠加
import { useEffect, useRef } from "react"
import { createChart, CandlestickSeries, LineSeries, HistogramSeries } from "lightweight-charts"
import { cn } from "@/lib/utils"

interface CandlestickData {
  time: number | string
  open: number
  high: number
  low: number
  close: number
}

interface MAData {
  time: number | string
  ma5: number | null
  ma10: number | null
  ma20: number | null
  ma60: number | null
}

interface BollingerData {
  time: number | string
  upper: number | null
  middle: number | null
  lower: number | null
}

interface VolumeData {
  time: number | string
  value: number
  color: string
}

interface CandlestickChartProps {
  data: CandlestickData[]
  maData?: MAData[]
  bollingerData?: BollingerData[]
  volumeData?: VolumeData[]
  showMA?: boolean
  showBollinger?: boolean
  showVolume?: boolean
  height?: number
  className?: string
}

export function buildPriceAutoscaleInfo(data: CandlestickData[]) {
  const prices = data.flatMap((item) => [item.high, item.low])
    .filter((price) => Number.isFinite(price) && price > 0)

  if (prices.length === 0) return null

  const minPrice = Math.min(...prices)
  const maxPrice = Math.max(...prices)
  const spread = Math.max(maxPrice - minPrice, maxPrice * 0.01)
  const padding = spread * 0.08

  return {
    priceRange: {
      minValue: Math.max(0, minPrice - padding),
      maxValue: maxPrice + padding,
    },
    margins: {
      above: 20,
      below: 20,
    },
  }
}

export function CandlestickChart({
  data,
  maData,
  bollingerData,
  volumeData,
  showMA = true,
  showBollinger = true,
  showVolume = true,
  height = 400,
  className,
}: CandlestickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<any>(null)
  const candlestickSeriesRef = useRef<any>(null)
  const dataRef = useRef<CandlestickData[]>(data)
  const maSeriesRef = useRef<Record<string, any>>({})
  const bollingerSeriesRef = useRef<Record<string, any>>({})
  const volumeSeriesRef = useRef<any>(null)

  dataRef.current = data

  // 创建图表和所有序列
  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height,
      layout: {
        background: { color: "transparent" },
        textColor: "#848e9c",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(42, 46, 57, 0.3)" },
        horzLines: { color: "rgba(42, 46, 57, 0.3)" },
      },
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: "rgba(197, 203, 206, 0.4)",
      },
      timeScale: {
        borderColor: "rgba(197, 203, 206, 0.4)",
        timeVisible: true,
        secondsVisible: false,
      },
    })

    // 成交量柱（先添加，在最底层）
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    })
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })
    volumeSeriesRef.current = volumeSeries

    // K 线
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#ef5350",
      downColor: "#26a69a",
      borderVisible: false,
      wickUpColor: "#ef5350",
      wickDownColor: "#26a69a",
      autoscaleInfoProvider: (baseImplementation: () => any) =>
        buildPriceAutoscaleInfo(dataRef.current) ?? baseImplementation(),
    })
    candlestickSeriesRef.current = candlestickSeries

    // MA 线
    const maColors: Record<string, string> = {
      ma5: "#F5A623",
      ma10: "#4A90D9",
      ma20: "#9B59B6",
      ma60: "#2ECC71",
    }
    for (const [key, color] of Object.entries(maColors)) {
      const series = chart.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })
      maSeriesRef.current[key] = series
    }

    // 布林带
    const bollingerSeries = chart.addSeries(LineSeries, {
      color: "rgba(155, 89, 182, 0.6)",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })
    bollingerSeriesRef.current["middle"] = bollingerSeries

    const bollUpperSeries = chart.addSeries(LineSeries, {
      color: "rgba(155, 89, 182, 0.3)",
      lineWidth: 1,
      lineStyle: 2, // dashed
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })
    bollingerSeriesRef.current["upper"] = bollUpperSeries

    const bollLowerSeries = chart.addSeries(LineSeries, {
      color: "rgba(155, 89, 182, 0.3)",
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })
    bollingerSeriesRef.current["lower"] = bollLowerSeries

    chartRef.current = chart

    // 响应式
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        })
      }
    }
    window.addEventListener("resize", handleResize)

    return () => {
      window.removeEventListener("resize", handleResize)
      chart.remove()
      chartRef.current = null
    }
  }, [height])

  // 更新数据
  useEffect(() => {
    if (!candlestickSeriesRef.current || data.length === 0) return

    // K 线数据
    candlestickSeriesRef.current.setData(data)

    // 成交量
    if (volumeData && volumeSeriesRef.current) {
      volumeSeriesRef.current.setData(volumeData)
    }

    // MA 线
    if (maData) {
      const filterValid = (key: string) =>
        maData
          .filter((d: any) => d[key] != null)
          .map((d: any) => ({ time: d.time, value: d[key] }))

      for (const key of ["ma5", "ma10", "ma20", "ma60"]) {
        if (maSeriesRef.current[key]) {
          maSeriesRef.current[key].setData(filterValid(key))
        }
      }
    }

    // 布林带
    if (bollingerData) {
      const filterValid = (key: string) =>
        bollingerData
          .filter((d: any) => d[key] != null)
          .map((d: any) => ({ time: d.time, value: d[key] }))

      for (const key of ["upper", "middle", "lower"]) {
        if (bollingerSeriesRef.current[key]) {
          bollingerSeriesRef.current[key].setData(filterValid(key))
        }
      }
    }

    // 自适应
    chartRef.current?.timeScale().fitContent()
  }, [data, maData, bollingerData, volumeData])

  // 切换可见性
  useEffect(() => {
    for (const series of Object.values(maSeriesRef.current)) {
      series?.applyOptions({ visible: showMA })
    }
  }, [showMA])

  useEffect(() => {
    for (const series of Object.values(bollingerSeriesRef.current)) {
      series?.applyOptions({ visible: showBollinger })
    }
  }, [showBollinger])

  useEffect(() => {
    volumeSeriesRef.current?.applyOptions({ visible: showVolume })
  }, [showVolume])

  return (
    <div
      ref={chartContainerRef}
      className={cn("w-full", className)}
      style={{ height: `${height}px` }}
    />
  )
}
