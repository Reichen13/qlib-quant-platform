// 个股概念板块归属卡片
import { useState, useEffect } from "react";
import { Tag } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

interface BoardItem { name: string; code: string; change_pct: string; lead_stock: string; }

export function StockConceptsCard({ code }: { code: string }) {
  const [boards, setBoards] = useState<BoardItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!code) return;
    setLoading(true);
    fetch(`/api/market/stocks/${code}/concepts`)
      .then(r => r.json())
      .then(d => setBoards(d.boards || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [code]);

  if (!code) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-1">
          <Tag className="h-4 w-4" /> 概念板块 ({boards.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? <Skeleton className="h-24 w-full" /> : boards.length === 0 ? (
          <p className="text-sm text-muted-foreground">暂无概念数据</p>
        ) : (
          <div className="flex flex-wrap gap-1.5 max-h-[140px] overflow-y-auto">
            {boards.map((b, i) => (
              <Badge key={i} variant="outline" className="text-xs cursor-default"
                title={b.lead_stock ? `龙头: ${b.lead_stock}` : undefined}>
                {b.name}
                {b.change_pct !== undefined && b.change_pct !== "" && (
                  <span className={`ml-1 ${Number(b.change_pct) >= 0 ? "text-red-500" : "text-green-500"}`}>
                    {Number(b.change_pct) >= 0 ? "+" : ""}{b.change_pct}%
                  </span>
                )}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
