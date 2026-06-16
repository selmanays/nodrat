"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/blocks/page-header";
import { TrendStatusBadge } from "@/components/blocks/trend-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  type ApiException,
  type ClusterListItem,
  type TrendState,
  listClusters,
} from "@/lib/api";

const PAGE_SIZE = 50;
const TREND_STATES = new Set(["breaking", "developing", "stable", "fading"]);

// #1570 arz: kümenin aynı entity'sinin canlı trend durumu + pencere haber sayısı
function ClusterTrendCell({ c }: { c: ClusterListItem }) {
  const s = c.trend_state;
  if (!s || s === "quiet") {
    return (
      <span className="text-xs text-muted-foreground">
        {s === "quiet" ? "Sessiz" : "—"}
      </span>
    );
  }
  if (!TREND_STATES.has(s)) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <div className="flex items-center gap-1.5">
      <TrendStatusBadge state={s as TrendState} />
      {c.article_count_window != null && c.article_count_window > 0 ? (
        <span className="text-xs text-muted-foreground">{c.article_count_window}</span>
      ) : null}
    </div>
  );
}

export default function AdminClustersPage() {
  const [items, setItems] = useState<ClusterListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await listClusters({
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        window: "24h", // #1570 trend zenginleştirme penceresi
      });
      setItems(resp.data ?? []);
      setTotal(resp.total ?? 0);
    } catch (err) {
      toast.error((err as ApiException).message || "Kümeler yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    void load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Araştırma Kümeleri"
        description="GLOBAL kanonik araştırma kümeleri (pivot Faz 3/6) — TALEP (üye/kullanıcı) × ARZ (#1570: aynı entity'nin canlı trend durumu, son 24s). Salt-okuma; içerik user-scoped. Atama gece 03:50 UTC. Trend kolonu için trends.enabled açık olmalı."
      />

      <Card>
        <CardContent className="pt-6">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Toplam <span className="font-medium">{total}</span> küme
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void load()}
              disabled={loading}
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              Yenile
            </Button>
          </div>

          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
              Henüz küme yok. Pivot kümeleme cold-start: flag
              (<code>research.clustering.enabled</code>) açık olmalı + gece
              batch (03:50 UTC) koşmalı + kullanıcı sorguları birikmeli.
              Geçmiş F0&apos;da silindiği için ilk gün boş olması beklenir.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Kanonik ad</TableHead>
                  <TableHead>Tip</TableHead>
                  <TableHead className="text-right">Üye</TableHead>
                  <TableHead className="text-right">Kullanıcı</TableHead>
                  <TableHead>Trend (24s)</TableHead>
                  <TableHead>Ebeveyn</TableHead>
                  <TableHead>Son aktivite</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((c) => (
                  <TableRow key={c.cluster_id}>
                    <TableCell className="font-medium">
                      {c.canonical_name}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{c.cluster_type}</Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {c.member_count}
                    </TableCell>
                    <TableCell className="text-right">
                      {c.distinct_users}
                    </TableCell>
                    <TableCell>
                      <ClusterTrendCell c={c} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {c.parent_cluster_id ? "↳ var" : "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {c.last_at
                        ? new Date(c.last_at).toLocaleString("tr-TR")
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1 || loading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Önceki
              </Button>
              <span className="text-sm text-muted-foreground">
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages || loading}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Sonraki
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
