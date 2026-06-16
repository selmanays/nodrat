"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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
  type GapsResponse,
  type TrendState,
  getClusterGaps,
  listClusters,
} from "@/lib/api";

const PAGE_SIZE = 50;
const TREND_STATES = new Set(["breaking", "developing", "stable", "fading"]);
const TYPE_LABEL: Record<string, string> = {
  person: "Kişi",
  org: "Kurum",
  place: "Yer",
  event: "Olay",
};

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
  const router = useRouter();
  const [items, setItems] = useState<ClusterListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [gaps, setGaps] = useState<GapsResponse | null>(null);

  useEffect(() => {
    getClusterGaps({ window: "24h", limit: 10 })
      .then(setGaps)
      .catch(() => setGaps(null));
  }, []);

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

      {gaps?.enabled &&
      (gaps.unmet_demand.length > 0 || gaps.rising_no_demand.length > 0) ? (
        <Card>
          <CardContent className="pt-6">
            <h3 className="text-sm font-semibold">Boşluk Radarı (son 24s)</h3>
            <p className="mb-4 mt-1 text-xs text-muted-foreground">
              Talep × arz uyumsuzluğu — editöryel öncelik sinyali (#1570 G).
            </p>
            <div className="grid gap-6 md:grid-cols-2">
              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">
                  Karşılanmamış ilgi · talep var, haber sessiz
                </p>
                {gaps.unmet_demand.length === 0 ? (
                  <p className="text-xs text-muted-foreground">—</p>
                ) : (
                  <ul className="space-y-1.5">
                    {gaps.unmet_demand.map((g) => (
                      <li key={g.cluster_key} className="space-y-0.5 text-sm">
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex min-w-0 items-center gap-1.5">
                            <span className="truncate">{g.canonical_name}</span>
                            <Badge variant="secondary" className="shrink-0">
                              {TYPE_LABEL[g.cluster_type] ?? g.cluster_type}
                            </Badge>
                          </span>
                          <span className="shrink-0 text-xs text-muted-foreground">
                            {g.distinct_users} kullanıcı · {g.article_count_window ?? 0} haber
                          </span>
                        </div>
                        {/* E-lite #1586: 30g tarihsel kapsayan kaynaklar → admin aksiyon */}
                        <p className="text-xs text-muted-foreground">
                          {g.coverage_sources.length > 0
                            ? `Kapsayan: ${g.coverage_sources
                                .map((c) => `${c.source_name} (${c.article_count})`)
                                .join(" · ")}`
                            : "Hiçbir kaynak kapsamıyor — yeni kaynak adayı"}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">
                  İlgisiz yükselen · haber kızışıyor, küme yok
                </p>
                {gaps.rising_no_demand.length === 0 ? (
                  <p className="text-xs text-muted-foreground">—</p>
                ) : (
                  <ul className="space-y-1.5">
                    {gaps.rising_no_demand.map((g) => (
                      <li
                        key={`${g.entity_type}:${g.entity_name}`}
                        className="flex items-center justify-between gap-2 text-sm"
                      >
                        <span className="flex min-w-0 items-center gap-1.5">
                          <span className="truncate">{g.entity_name}</span>
                          <Badge variant="secondary" className="shrink-0">
                            {TYPE_LABEL[g.entity_type] ?? g.entity_type}
                          </Badge>
                        </span>
                        <span className="flex shrink-0 items-center gap-1.5">
                          {TREND_STATES.has(g.trend_state) ? (
                            <TrendStatusBadge state={g.trend_state as TrendState} />
                          ) : null}
                          <span className="text-xs text-muted-foreground">{g.article_count}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}

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
                  <TableRow
                    key={c.cluster_id}
                    className="cursor-pointer"
                    onClick={() => router.push(`/admin/clusters/${c.cluster_id}`)}
                  >
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
