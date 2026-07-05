// 龙虎榜页面 - 全市场 + 个股查询
import { useState, useEffect } from "react";
import { Search, TrendingUp, TrendingDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

interface DragonTigerRecord {
  date: string; code: string; name: string; price: string;
  change_pct: string; net_buy_amt: number; reason: string; amount: number;
}

export function DragonTigerPage() {
  const [records, setRecords] = useState<DragonTigerRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchCode, setSearchCode] = useState("");
  const [error, setError] = useState("");

  const fetchData = async (code?: string) => {
    setLoading(true);
    setError("");
    try {
      const url = code
        ? `/api/market/dragon-tiger?code=${code}&limit=30`
        : "/api/market/dragon-tiger?limit=30";
      const res = await fetch(url);
      const data = await res.json();
      setRecords(data.records || []);
    } catch (e) {
      setError("数据加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-bold">龙虎榜</h1>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            上榜股票 {records.length > 0 && `(${records.length} 只)`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2 mb-4">
            <Input
              placeholder="输入股票代码（如 600519）"
              value={searchCode}
              onChange={(e) => setSearchCode(e.target.value)}
              className="max-w-[200px]"
            />
            <Button size="sm" onClick={() => fetchData(searchCode || undefined)}>
              <Search className="h-4 w-4 mr-1" /> 查询
            </Button>
            {searchCode && (
              <Button size="sm" variant="outline" onClick={() => { setSearchCode(""); fetchData(); }}>
                查看全市场
              </Button>
            )}
          </div>

          {loading ? (
            <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
          ) : error ? (
            <p className="text-red-500">{error}</p>
          ) : records.length === 0 ? (
            <p className="text-muted-foreground">暂无龙虎榜数据</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4">日期</th>
                    <th className="py-2 pr-4">股票</th>
                    <th className="py-2 pr-4">涨跌幅</th>
                    <th className="py-2 pr-4">净买入(万)</th>
                    <th className="py-2 pr-4">成交额(万)</th>
                    <th className="py-2">上榜原因</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((r, i) => (
                    <tr key={i} className="border-b hover:bg-muted/50">
                      <td className="py-2 pr-4">{r.date}</td>
                      <td className="py-2 pr-4 font-medium">{r.name} <span className="text-muted-foreground">{r.code}</span></td>
                      <td className="py-2 pr-4">
                        <span className={Number(r.change_pct) >= 0 ? "text-red-500" : "text-green-500"}>
                          {Number(r.change_pct) >= 0 ? <TrendingUp className="inline h-3 w-3 mr-1" /> : <TrendingDown className="inline h-3 w-3 mr-1" />}
                          {r.change_pct}%
                        </span>
                      </td>
                      <td className="py-2 pr-4">{r.net_buy_amt > 0 ? <span className="text-red-500">+{r.net_buy_amt}</span> : r.net_buy_amt}</td>
                      <td className="py-2 pr-4 text-muted-foreground">{r.amount}</td>
                      <td className="py-2"><Badge variant="outline" className="text-xs">{r.reason}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
