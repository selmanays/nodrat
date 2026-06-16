"use client";

/**
 * Admin Küme Detayı (#1579 F) — talep + trend timeline/haberler.
 *
 * Bir araştırma kümesinin TALEP (üye/distinct kullanıcı) + ARZ (aynı entity'nin
 * trend durumu + pencere-içi timeline + son haberler + kaynak dağılımı) detayı.
 * Read-only. trends.enabled OFF → arz boş.
 */

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ExternalLink, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/blocks/page-header";
import { TrendSparkline } from "@/components/blocks/trend-sparkline";
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
  type ClusterDetailResponse,
  type TrendState,
  getClusterDetail,
} from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  person: "Kişi",
  org: "Kurum",
  place: "Yer",
  event: "Olay",
};
const TREND_STATES = new Set(["breaking", "developing", "stable", "fading"]);

function fmt(n: number): string {
  return n.toLocaleString("tr-TR");
}

function StatCard({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-xs text-muted-foreground">{label}</p>
        <div className="mt-1 text-2xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  );
}

export default function AdminClusterDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const win = search.get("window") ?? "24h";
  const [d, setD] = useState<ClusterDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setD(await getClusterDetail(params.id, { window: win }));
    } catch (e) {
      toast.error((e as ApiException).message || "Küme detayı yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [params.id, win]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => router.push("/admin/clusters")}>
          <ArrowLeft className="mr-1 h-4 w-4" />
          Kümeler
        </Button>
        <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Yenile
        </Button>
      </div>

      {loading || !d ? (
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <>
          <PageHeader
            title={d.canonical_name}
            description={`Araştırma kümesi — talep (kullanıcı ilgisi) × arz (haber trendi, son ${win}). Anahtar: ${d.cluster_key}`}
          />
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{TYPE_LABEL[d.cluster_type] ?? d.cluster_type}</Badge>
            {d.parent_cluster_id ? <Badge variant="outline">alt konu</Badge> : null}
            {d.deprecated ? <Badge variant="outline">deprecated</Badge> : null}
          </div>

          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label="Üye (sorgu)" value={fmt(d.member_count)} />
            <StatCard label="İlgilenen kullanıcı" value={fmt(d.distinct_users)} />
            <StatCard
              label="Trend durumu"
              value={
                d.trend_state && TREND_STATES.has(d.trend_state) ? (
                  <TrendStatusBadge state={d.trend_state as TrendState} />
                ) : (
                  <span className="text-base text-muted-foreground">Sessiz</span>
                )
              }
            />
            <StatCard label={`Haber (${win})`} value={fmt(d.article_count_window ?? 0)} />
          </div>

          {d.sparkline.length > 0 ? (
            <Card>
              <CardContent className="pt-6">
                <p className="mb-3 text-sm font-medium">Haber zaman serisi ({win})</p>
                <TrendSparkline data={d.sparkline} />
              </CardContent>
            </Card>
          ) : null}

          {d.sources.length > 0 ? (
            <Card>
              <CardContent className="pt-6">
                <p className="mb-3 text-sm font-medium">Kaynak dağılımı</p>
                <div className="flex flex-wrap gap-2">
                  {d.sources.map((s) => (
                    <Badge key={s.source_name ?? "?"} variant="outline" className="font-normal">
                      {s.source_name ?? "—"}
                      <span className="ml-1.5 text-muted-foreground">{s.article_count}</span>
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          ) : null}

          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Haber</TableHead>
                    <TableHead className="w-[160px]">Kaynak</TableHead>
                    <TableHead className="w-[160px]">Yayın</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {d.articles.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3} className="py-8 text-center text-muted-foreground">
                        Bu pencerede haber yok.
                      </TableCell>
                    </TableRow>
                  ) : (
                    d.articles.map((a) => (
                      <TableRow key={a.id}>
                        <TableCell className="font-medium">
                          {a.url ? (
                            <a
                              href={a.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 hover:underline"
                            >
                              {a.title}
                              <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground" />
                            </a>
                          ) : (
                            a.title
                          )}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {a.source_name ?? "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {a.published_at
                            ? new Date(a.published_at).toLocaleString("tr-TR")
                            : "—"}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
