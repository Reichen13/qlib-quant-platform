// 个股资金流向卡片
import { useState, useEffect } from "react";
import { TrendingUp, TrendingDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface FundFlowRecord { date: string; 主力净流入: number; 超大单净流入: number; 大单净流入: number; }

export function FundFlowCard({ code }: { code: string }) {
  const [records, setRecords] = useState<FundFlowRecord[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!code) return;
    setLoading(true);
    fetch(`/api/market/stocks/${code}/fund-flow?days=10`)
      .then(r => r.json())
      .then(d => setRecords(d.records || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [code]);

  if (!code) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">资金流向 (近10日)</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? <Skeleton className="h-32 w-full" /> : records.length === 0 ? (
          <p className="text-sm text-muted-foreground">暂无数据</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="border-b text-muted-foreground">
                <th className="py-1 text-left">日期</th>
                <th className="py-1 text-right">主力净流入(万)</th>
                <th className="py-1 text-right">超大单(万)</th>
                <th className="py-1 text-right">大单(万)</th>
              </tr></thead>
              <tbody>
                {records.slice(-5).reverse().map((r, i) => (
                  <tr key={i} className="border-b hover:bg-muted/50">
                    <td className="py-1">{r.date}</td>
                    <td className={`py-1 text-right ${r.主力净流入 > 0 ? "text-red-500" : "text-green-500"}`}>
                      {r.主力净流入 > 0 ? <TrendingUp className="inline h-3 w-3 mr-1" /> : <TrendingDown className="inline h-3 w-3 mr-1" />}
                      {r.主力净流入}
                    </td>
                    <td className="py-1 text-right">{r.超大单净流入}</td>
                    <td className="py-1 text-right">{r.大单净流入}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
