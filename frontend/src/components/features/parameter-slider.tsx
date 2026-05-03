// 参数滑块组件 - 用于策略配置
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Slider } from "@/components/ui/slider"
import { Badge } from "@/components/ui/badge"

export interface SliderConfig {
  id: string
  name: string
  value: number
  min: number
  max: number
  step: number
  unit?: string
  color: string
  description?: string
}

export interface ParameterSliderProps {
  title?: string
  description?: string
  sliders: SliderConfig[]
  totalLabel?: string
  onChange?: (id: string, value: number) => void
  showTotal?: boolean
  readOnly?: boolean
}

export function ParameterSlider({
  title,
  description,
  sliders,
  totalLabel = "总计",
  onChange,
  showTotal = true,
  readOnly = false,
}: ParameterSliderProps) {
  const total = sliders.reduce((sum, s) => sum + s.value, 0)

  const handleChange = (id: string, value: number[]) => {
    if (onChange && !readOnly) {
      onChange(id, value[0])
    }
  }

  return (
    <Card>
      {(title || description) && (
        <CardHeader>
          {title && <CardTitle>{title}</CardTitle>}
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
      )}
      <CardContent className="space-y-6">
        {sliders.map((slider) => (
          <div key={slider.id} className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor={slider.id} className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: slider.color }}
                />
                {slider.name}
              </Label>
              <Badge variant="outline" style={{ borderColor: slider.color }}>
                {slider.value}
                {slider.unit}
              </Badge>
            </div>
            {slider.description && (
              <p className="text-xs text-muted-foreground">{slider.description}</p>
            )}
            <Slider
              id={slider.id}
              min={slider.min}
              max={slider.max}
              step={slider.step}
              value={[slider.value]}
              onValueChange={(v) => handleChange(slider.id, v)}
              disabled={readOnly}
              className="my-2"
              style={{
                '--slider-thumb-color': slider.color,
              } as React.CSSProperties}
            />
          </div>
        ))}

        {showTotal && sliders.length > 1 && (
          <div className="pt-4 border-t">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{totalLabel}</span>
              <Badge variant="default" className="text-base px-3 py-1">
                {total}
                {sliders[0]?.unit}
              </Badge>
            </div>
            {total !== 100 && sliders[0]?.unit === "%" && (
              <p className="text-xs text-muted-foreground mt-1">
                {total < 100 && `剩余 ${(100 - total).toFixed(0)}% 未分配`}
                {total > 100 && `超出 ${(total - 100).toFixed(0)}%`}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
