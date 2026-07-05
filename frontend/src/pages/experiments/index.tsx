import { useState, useEffect } from "react";
import { FlaskConical, Filter, Zap } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

interface RunRecord {
  run_id: string; run_name: string; start_time: string;
  metrics: Record<string, number>; params: Record<string, string>;
  tags: Record<string, string>; experiment?: string;
}

interface Experiment {
  experiment_id: string; name: string; runs: RunRecord[];
}

const REGIME_COLORS: Record<string, string> = {
  bull: "text-red-500", correction: "text-amber-500", bear: "text-green-500", neutral: "text-blue-500",
};
const REGIME_LABELS: Record<string, string> = {
  bull: "牛市", correction: "回调", bear: "熊市", neutral: "震荡",
};

export function ExperimentsPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [bestRuns, setBestRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterRegime, setFilterRegime] = useState("");
  const [sortMetric, setSortMetric] = useState("metrics.sharpe_ratio");

  useEffect(() => {
    fetch("/api/experiments/experiments")
      .then(r => r.json())
      .then(d => setExperiments(d.experiments || []))
      .catch(() => {})
      .finally(() => setLoading(false));
    fetchBest();
  }, []);

  const fetchBest = (regime: string = "") => {
    const params = new URLSearchParams({ limit: "10", metric: sortMetric });
    if (regime) params.set("regime", regime);
    fetch(`/api/experiments/best?${params}`)
      .then(r => r.json())
      .then(d => setBestRuns(d.runs || []))
      .catch(() => {});
  };

  useEffect(() => { fetchBest(filterRegime); }, [filterRegime, sortMetric]);

  const totalRuns = experiments.reduce((s, e) => s + e.runs.length, 0);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FlaskConical className="h-6 w-6 text-purple-600" /> 实验看板
          </h1>
          <p className="text-muted-foreground">MLflow 回测实验对比 · {totalRuns} 次运行</p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={sortMetric} onValueChange={setSortMetric}>
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="排序指标" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="metrics.sharpe_ratio">夏普比率</SelectItem>
              <SelectItem value="metrics.annual_return">年化收益</SelectItem>
              <SelectItem value="metrics.max_drawdown">最大回撤</SelectItem>
              <SelectItem value="metrics.win_rate">胜率</SelectItem>
              <SelectItem value="metrics.calmar">Calmar</SelectItem>
            </SelectContent>
          </Select>
          <Select value={filterRegime || "全部"} onValueChange={(v) => setFilterRegime(v === "全部" ? "" : v)}>
            <SelectTrigger className="w-[130px]">
              <Filter className="h-4 w-4 mr-1" />
              <SelectValue placeholder="市场环境" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="全部">全部</SelectItem>
              <SelectItem value="bull">牛市</SelectItem>
              <SelectItem value="correction">回调</SelectItem>
              <SelectItem value="bear">熊市</SelectItem>
              <SelectItem value="neutral">震荡</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-1">
            <Zap className="h-4 w-4 text-amber-500" />
            最佳运行 {filterRegime && `(${REGIME_LABELS[filterRegime] || filterRegime})`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? <Skeleton className="h-48 w-full" /> : bestRuns.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              还没有回测记录，运行一次回测后这里会显示结果
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-2">策略</th>
                    <th className="py-2 pr-2">时间</th>
                    <th className="py-2 pr-2 text-right">年化收益</th>
                    <th className="py-2 pr-2 text-right">夏普</th>
                    <th className="py-2 pr-2 text-right">最大回撤</th>
                    <th className="py-2 pr-2 text-right">胜率</th>
                    <th className="py-2">市场环境</th>
                  </tr>
                </thead>
                <tbody>
                  {bestRuns.map((r, i) => {
                    const regime = r.tags?.market_regime || "neutral";
                    const ret = r.metrics?.annual_return ?? 0;
                    const sharpe = r.metrics?.sharpe_ratio ?? 0;
                    const dd = r.metrics?.max_drawdown ?? 0;
                    const wr = r.metrics?.win_rate ?? 0;
                    return (
                      <tr key={i} className="border-b hover:bg-muted/50">
                        <td className="py-2 pr-2 font-medium">{r.experiment || r.tags?.strategy || "—"}</td>
                        <td className="py-2 pr-2 text-muted-foreground">{r.run_name?.slice(-16) || "—"}</td>
                        <td className={`py-2 pr-2 text-right ${ret >= 0 ? "text-red-500" : "text-green-500"}`}>
                          {(ret * 100).toFixed(1)}%
                        </td>
                        <td className="py-2 pr-2 text-right">{sharpe.toFixed(2)}</td>
                        <td className="py-2 pr-2 text-right text-green-500">{(dd * 100).toFixed(1)}%</td>
                        <td className="py-2 pr-2 text-right">{(wr * 100).toFixed(0)}%</td>
                        <td className="py-2">
                          <Badge variant="outline" className={`text-xs ${REGIME_COLORS[regime] || ""}`}>
                            {REGIME_LABELS[regime] || regime}
                          </Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {experiments.filter(e => e.runs.length > 0).map(exp => (
        <Card key={exp.experiment_id}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{exp.name}</CardTitle>
            <CardDescription>{exp.runs.length} 次运行</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
              {exp.runs.slice(0, 6).map((r, i) => {
                const regime = r.tags?.market_regime || "neutral";
                return (
                  <div key={i} className="bg-muted/30 rounded p-2 text-center">
                    <div className="text-xs text-muted-foreground truncate">{r.run_name?.slice(-12) || "—"}</div>
                    <div className={`text-sm font-bold ${(r.metrics?.annual_return ?? 0) >= 0 ? "text-red-500" : "text-green-500"}`}>
                      {((r.metrics?.annual_return ?? 0) * 100).toFixed(1)}%
                    </div>
                    <Badge variant="outline" className={`text-[10px] mt-1 ${REGIME_COLORS[regime] || ""}`}>
                      {REGIME_LABELS[regime] || regime}
                    </Badge>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      ))}

      {!loading && experiments.length === 0 && (
        <Card className="border-dashed">
          <CardContent className="py-8 text-center text-muted-foreground">
            <FlaskConical className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p>还没有任何回测实验记录</p>
            <p className="text-sm mt-1">去「模型回测」页面运行一次回测，数据会自动记录到这里</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
