"use client";

/**
 * Admin Trend Overview — Trend Intelligence Faz 1 (#1500).
 *
 * Transient read-only: backend mevcut event_clusters/event_articles'tan CANLI
 * SQL ile hesaplar (persistence yok). Flag `trends.enabled` OFF → no-op
 * (enabled:false) → "kapalı" mesajı. clusters/page.tsx list deseni.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, TrendingUp } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/blocks/page-header";
import { TrendSparkline } from "@/components/blocks/trend-sparkline";
import { TrendStatusBadge } from "@/components/blocks/trend-status-badge";
import { TrendWindowToggle } from "@/components/blocks/trend-window-toggle";
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
  type TrendListItem,
  type TrendWindow,
  listTrends,
} from "@/lib/api";

const PAGE_SIZE = 50;

function fmt(n: number): string {
  return n.toLocaleString("tr-TR");
}

function MomentumCell({ value }: { value: number | null }) {
  if (value === null) {
    return (
      <Badge
        variant="outline"
        className="border-transparent bg-red-500/15 text-red-600 dark:text-red-400"
      >
        Yeni
      </Badge>
    );
  }
  const pct = Math.round(value * 100);
  const sign = pct > 0 ? "+" : "";
  const cls =
    pct > 0
      ? "text-emerald-600 dark:text-emerald-400"
      : pct < 0
        ? "text-red-600 dark:text-red-400"
        : "text-muted-foreground";
  return <span className={cls}>{`${sign}${fmt(pct)}%`}</span>;
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="mt-1 text-2xl font-semibold">{value}</p>
      </CardContent>
    </Card>
  );
}

export default function AdminTrendsPage() {
  const [items, setItems] = useState<TrendListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [enabled, setEnabled] = useState(true);
  const [trendWindow, setTrendWindow] = useState<TrendWindow>("24h");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await listTrends({
        window: trendWindow,
        sort: "momentum",
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
      setItems(resp.data ?? []);
      setTotal(resp.total ?? 0);
      setEnabled(resp.enabled);
    } catch (err) {
      toast.error((err as ApiException).message || "Trendler yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [trendWindow, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const summary = useMemo(() => {
    const breaking = items.filter(
      (t) => t.trend_state === "breaking" || t.trend_state === "developing",
    ).length;
    const articles = items.reduce((a, t) => a + t.article_count, 0);
    const sources = items.reduce((a, t) => a + t.unique_source_count, 0);
    return { breaking, articles, sources };
  }, [items]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Trendler"
        description="Trend Intelligence Faz 1 — mevcut haber kümelerinden CANLI hesaplanan konu trendleri (read-only, kalıcı kayıt yok). Hacim, momentum, kaynak çeşitliliği, novelty ve durum (patlıyor/gelişiyor/sabit/sönüyor)."
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <TrendWindowToggle
          value={trendWindow}
          onChange={(w) => {
            setPage(1);
            setTrendWindow(w);
          }}
          disabled={loading}
        />
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

      {enabled && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard label="Toplam trend (pencere)" value={fmt(total)} />
          <StatCard label="Patlıyor + gelişiyor (sayfa)" value={fmt(summary.breaking)} />
          <StatCard label="Toplam haber (sayfa)" value={fmt(summary.articles)} />
          <StatCard label="Kaynak toplamı (sayfa)" value={fmt(summary.sources)} />
        </div>
      )}

      <Card>
        <CardContent className="pt-6">
          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : !enabled ? (
            <div className="flex flex-col items-center gap-2 rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
              <TrendingUp className="h-6 w-6" />
              <p>
                Trend Intelligence kapalı. Açmak için{" "}
                <code>trends.enabled</code> ayarını{" "}
                <code>/admin/settings/trends</code> altından etkinleştirin.
              </p>
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
              Bu pencere için trend yok. Daha geniş bir zaman aralığı deneyin
              veya haber kümelenmesinin (event_clusters) dolmasını bekleyin.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Konu</TableHead>
                  <TableHead>Durum</TableHead>
                  <TableHead className="text-right">Haber</TableHead>
                  <TableHead className="text-right">Momentum</TableHead>
                  <TableHead className="text-right">Kaynak</TableHead>
                  <TableHead className="text-right">Novelty</TableHead>
                  <TableHead className="text-right">Güvenilirlik</TableHead>
                  <TableHead>Eğilim</TableHead>
                  <TableHead>Son görülme</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((t) => (
                  <TableRow key={t.cluster_id}>
                    <TableCell className="max-w-xs truncate font-medium" title={t.title}>
                      {t.title}
                    </TableCell>
                    <TableCell>
                      <TrendStatusBadge state={t.trend_state} />
                    </TableCell>
                    <TableCell className="text-right">
                      {fmt(t.article_count)}
                      {t.previous_article_count > 0 && (
                        <span className="ml-1 text-xs text-muted-foreground">
                          ({fmt(t.previous_article_count)})
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <MomentumCell value={t.momentum} />
                    </TableCell>
                    <TableCell className="text-right">
                      {fmt(t.unique_source_count)}
                      <span className="ml-1 text-xs text-muted-foreground">
                        ({t.source_diversity.toFixed(2)})
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      {t.novelty_score.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right">
                      {t.credibility_score !== null
                        ? t.credibility_score.toFixed(2)
                        : "—"}
                    </TableCell>
                    <TableCell>
                      <TrendSparkline data={t.sparkline} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {t.last_seen_at
                        ? new Date(t.last_seen_at).toLocaleString("tr-TR")
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {enabled && totalPages > 1 && (
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
