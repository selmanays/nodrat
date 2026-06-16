"use client";

/**
 * Admin Trend Detail (drill-down) — #1552.
 *
 * Bir entity'ye (canonical veya ham) tıklayınca: pencere içi haberler, kaynak
 * dağılımı, varyant yüzey biçimleri, zaman-serisi. Read-only.
 */

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ExternalLink, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/blocks/page-header";
import { TrendSparkline } from "@/components/blocks/trend-sparkline";
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
  type TrendDetailResponse,
  type TrendWindow,
  getTrendDetail,
} from "@/lib/api";

const ENTITY_TYPE_LABEL: Record<string, string> = {
  person: "Kişi",
  org: "Kurum",
  place: "Yer",
  event: "Olay",
};

function fmt(n: number): string {
  return n.toLocaleString("tr-TR");
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

export default function AdminTrendDetailPage() {
  const router = useRouter();
  const params = useParams<{ key: string }>();
  const search = useSearchParams();
  const key = decodeURIComponent(params.key);
  const win = (search.get("window") as TrendWindow) || "24h";

  const [detail, setDetail] = useState<TrendDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await getTrendDetail({ key, window: win, limit: 100 });
      setDetail(resp);
    } catch (err) {
      toast.error((err as ApiException).message || "Detay yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [key, win]);

  useEffect(() => {
    void load();
  }, [load]);

  const typeLabel = detail
    ? (ENTITY_TYPE_LABEL[detail.entity_type] ?? detail.entity_type)
    : "";

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" onClick={() => router.push("/admin/trends")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Trendler
        </Button>
        <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Yenile
        </Button>
      </div>

      <PageHeader
        title={detail?.entity_name ?? key}
        description={
          detail
            ? `${typeLabel} · son ${detail.window} · ${detail.canonical ? "birleşik (canonical)" : "ham entity"}`
            : "Trend detayı"
        }
      />

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : !detail ? (
        <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
          Bu entity için veri bulunamadı.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label="Toplam haber" value={fmt(detail.total_articles)} />
            <StatCard label="Kaynak sayısı" value={fmt(detail.unique_sources)} />
            <StatCard label="Varyant biçim" value={fmt(detail.variants.length)} />
            <Card>
              <CardContent className="pt-6">
                <p className="text-xs text-muted-foreground">Eğilim</p>
                <div className="mt-2">
                  <TrendSparkline data={detail.sparkline} />
                </div>
              </CardContent>
            </Card>
          </div>

          {detail.canonical && detail.variants.length > 1 && (
            <Card>
              <CardContent className="pt-6">
                <p className="mb-3 text-sm font-medium">
                  Birleştirilen biçimler ({detail.variants.length})
                </p>
                <div className="flex flex-wrap gap-2">
                  {detail.variants.map((v) => (
                    <Badge key={v.entity_normalized} variant="secondary" className="font-normal">
                      {v.surface_form}
                      <span className="ml-1 text-muted-foreground">{fmt(v.article_count)}</span>
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-1">
              <CardContent className="pt-6">
                <p className="mb-3 text-sm font-medium">Kaynak dağılımı</p>
                <div className="space-y-1">
                  {detail.sources.map((s) => (
                    <div
                      key={s.source_name ?? "?"}
                      className="flex items-center justify-between text-sm"
                    >
                      <span className="truncate">{s.source_name ?? "—"}</span>
                      <span className="text-muted-foreground">{fmt(s.article_count)}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card className="lg:col-span-2">
              <CardContent className="pt-6">
                <p className="mb-3 text-sm font-medium">Haberler ({detail.articles.length})</p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Başlık</TableHead>
                      <TableHead>Kaynak</TableHead>
                      <TableHead>Yayın</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {detail.articles.map((a) => (
                      <TableRow key={a.id}>
                        <TableCell className="max-w-md font-medium">
                          {a.url ? (
                            <a
                              href={a.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 hover:underline"
                            >
                              <span className="truncate">{a.title}</span>
                              <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground" />
                            </a>
                          ) : (
                            <span className="truncate">{a.title}</span>
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
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
