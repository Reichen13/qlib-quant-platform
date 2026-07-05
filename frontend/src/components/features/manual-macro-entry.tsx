// 宏观指标手动录入组件 - 自包含，不依赖父组件 props
import { useState, useEffect } from "react";
import { Save, RefreshCw, Pencil } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

const INDICATOR_META: Record<string, { label: string; unit: string; hint: string }> = {
  M2_YOY: { label: "M2 同比增速", unit: "%", hint: "中国人民银行每月公布" },
  SHIBOR_ON: { label: "SHIBOR 隔夜", unit: "%", hint: "银行间拆借利率" },
  SHIBOR_1M: { label: "SHIBOR 1月", unit: "%", hint: "银行间拆借利率" },
  BOND_10Y: { label: "10 年国债收益率", unit: "%", hint: "中国10年期国债到期收益率" },
};

export function ManualMacroEntry() {
  const [values, setValues] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    api.macro.manualGet().then((data) => {
      if (data && Object.keys(data).length > 0) {
        const v: Record<string, string> = {};
        Object.entries(INDICATOR_META).forEach(([key]) => {
          if (data[key] !== undefined) v[key] = String(data[key]);
        });
        setValues((prev) => ({ ...prev, ...v }));
      }
    }).catch(() => {});
  }, []);

  const handleSave = async () => {
    setLoading(true);
    const numeric: Record<string, number> = {};
    Object.entries(values).forEach(([k, v]) => {
      if (v && v.trim()) numeric[k] = parseFloat(v);
    });
    try {
      await api.macro.manualSave(numeric);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {}
    setLoading(false);
  };

  const keys = Object.keys(INDICATOR_META);
  const hasValues = keys.some((k) => values[k] && values[k].trim());

  return (
    <Card className="border-dashed">
      <CardHeader className="pb-2 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <CardTitle className="text-sm flex items-center gap-1">
          <Pencil className="h-4 w-4" />
          手动录入宏观指标
          {hasValues && <span className="text-xs text-green-600 ml-2">(已录入 {keys.filter(k => values[k]).length}/{keys.length})</span>}
        </CardTitle>
      </CardHeader>
      {expanded && (
        <CardContent>
          <div className="grid gap-3 md:grid-cols-2">
            {keys.map((key) => (
              <div key={key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">
                  {INDICATOR_META[key].label} ({INDICATOR_META[key].unit})
                </Label>
                <Input
                  type="number"
                  step="0.01"
                  placeholder={INDICATOR_META[key].hint}
                  value={values[key] || ""}
                  onChange={(e) => setValues({ ...values, [key]: e.target.value })}
                  className="h-8 text-sm"
                />
              </div>
            ))}
          </div>
          <div className="flex gap-2 mt-3">
            <Button size="sm" onClick={handleSave} disabled={loading}>
              {saved ? <RefreshCw className="h-3 w-3 mr-1" /> : <Save className="h-3 w-3 mr-1" />}
              {saved ? "已保存" : "保存"}
            </Button>
            {saved && (
              <Button size="sm" variant="outline" onClick={() => window.location.reload()}>
                <RefreshCw className="h-3 w-3 mr-1" /> 刷新页面查看效果
              </Button>
            )}
          </div>
        </CardContent>
      )}
    </Card>
  );
}
