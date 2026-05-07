"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Database,
  FileText,
  Plus,
  Scale,
  Search,
  ServerCog,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from "@/components/ui/item";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  ApiException,
  adminSettingsList,
  articleStats,
  dashboardHourly,
  dashboardProviderCalls,
  getAdminUserStats,
  getQueueOverview,
  listSources,
  listTakedownRequests,
  type AdminUserStatsResponse,
  type ArticleStatsResponse,
  type DashboardHourlyResponse,
  type ProviderCallsPeriod,
  type ProviderCallsRangeResponse,
  type QueueOverviewResponse,
  type SourcePublic,
} from "@/lib/api";
import {
  DashboardAreaChartCard,
  DashboardAreaChartCardSkeleton,
} from "@/components/blocks/dashboard-area-chart-card";
import {
  DashboardStatCard,
  DashboardStatCardSkeleton,
} from "@/components/blocks/dashboard-stat-card";
import { Skeleton } from "@/components/ui/skeleton";

const PROVIDER_FALLBACK_LABELS: Record<string, string> = {
  deepseek_v3: "deepseek-v4-flash",
  // Embedding (#350 migration tamam, #420 NIM kaldırıldı — tek provider)
  local_bge_m3: "bge-m3 (local)",
  // Rerank (#347 MVP-1.5)
  local_bge_reranker: "bge-reranker-v2-m3 (local)",
  nim_rerank: "rerank-qa-mistral-4b (NIM yedek)",
  // VLM
  nim_vlm: "Llama 4 Maverick (NIM)",
  anthropic: "claude",
  openai: "openai",
};

interface DashboardData {
  articles: ArticleStatsResponse | null;
  users: AdminUserStatsResponse | null;
  queue: QueueOverviewResponse | null;
  sources: SourcePublic[];
  openTakedowns: number;
  hourly: DashboardHourlyResponse | null;
}

type SourceView = "rss" | "dom";

const SOURCE_TYPE_LABEL: Record<string, string> = {
  rss: "RSS",
  category_page: "DOM",
  manual: "Manuel",
};

export default function AdminLandingPage() {
  const [data, setData] = useState<DashboardData>({
    articles: null,
    users: null,
    queue: null,
    sources: [],
    openTakedowns: 0,
    hourly: null,
  });
  const [loading, setLoading] = useState(true);
  const [sourceView, setSourceView] = useState<SourceView>("rss");
  const [sourceQuery, setSourceQuery] = useState("");
  const [llmPeriod, setLlmPeriod] = useState<ProviderCallsPeriod>("7d");
  const [llmRange, setLlmRange] =
    useState<ProviderCallsRangeResponse | null>(null);
  const [providerLabels, setProviderLabels] = useState<Record<string, string>>(
    PROVIDER_FALLBACK_LABELS,
  );

  useEffect(() => {
    let cancelled = false;
    void dashboardProviderCalls(llmPeriod)
      .then((r) => {
        if (!cancelled) setLlmRange(r);
      })
      .catch(() => {
        if (!cancelled) setLlmRange(null);
      });
    return () => {
      cancelled = true;
    };
  }, [llmPeriod]);

  useEffect(() => {
    let cancelled = false;
    void adminSettingsList("llm")
      .then((r) => {
        if (cancelled) return;
        const map = Object.fromEntries(r.data.map((s) => [s.key, s.value]));
        setProviderLabels({
          ...PROVIDER_FALLBACK_LABELS,
          deepseek_v3:
            String(
              map["llm.deepseek_chat_model"] ?? PROVIDER_FALLBACK_LABELS.deepseek_v3,
            ),
          nim_rerank:
            String(
              map["llm.nim_rerank_model"] ?? PROVIDER_FALLBACK_LABELS.nim_rerank,
            ),
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    void loadAll();
  }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [articles, users, queue, sourcesList, submitted, triaging, investigating, hourly] =
        await Promise.allSettled([
          articleStats(),
          getAdminUserStats(),
          getQueueOverview(),
          listSources({ limit: 200 }),
          listTakedownRequests({ status: "submitted", limit: 1 }),
          listTakedownRequests({ status: "triaging", limit: 1 }),
          listTakedownRequests({ status: "investigating", limit: 1 }),
          dashboardHourly(),
        ]);

      const openTakedowns =
        (submitted.status === "fulfilled" ? submitted.value.total : 0) +
        (triaging.status === "fulfilled" ? triaging.value.total : 0) +
        (investigating.status === "fulfilled" ? investigating.value.total : 0);

      setData({
        articles: articles.status === "fulfilled" ? articles.value : null,
        users: users.status === "fulfilled" ? users.value : null,
        queue: queue.status === "fulfilled" ? queue.value : null,
        sources:
          sourcesList.status === "fulfilled" ? sourcesList.value : [],
        openTakedowns,
        hourly: hourly.status === "fulfilled" ? hourly.value : null,
      });
    } catch (e) {
      if (e instanceof ApiException) {
        console.error("dashboard load fail", e);
      }
    } finally {
      setLoading(false);
    }
  }

  const activeSources = data.sources.filter((s) => s.is_active).length;
  const totalSources = data.sources.length;
  const queuedJobs =
    data.queue?.queues.reduce((sum, q) => sum + q.queued_count, 0) ?? 0;
  const runningJobs =
    data.queue?.queues.reduce((sum, q) => sum + q.running_count, 0) ?? 0;
  const failedUnresolved = data.queue?.failed_jobs_unresolved ?? 0;

  const topSources = useMemo(() => {
    if (!data.articles?.by_source) return [];
    const sourceMap = new Map(data.sources.map((s) => [s.slug, s]));
    const wantedType = sourceView === "rss" ? "rss" : "category_page";
    const q = sourceQuery.trim().toLowerCase();
    return data.articles.by_source
      .map((row) => {
        const meta = sourceMap.get(row.slug);
        return {
          slug: row.slug,
          name: row.name,
          count: row.count,
          type: meta?.type ?? "rss",
          category: meta?.category ?? null,
          domain: meta?.domain ?? null,
        };
      })
      .filter((s) => s.type === wantedType)
      .filter((s) =>
        q
          ? s.name.toLowerCase().includes(q) ||
            s.slug.toLowerCase().includes(q) ||
            (s.category?.toLowerCase().includes(q) ?? false)
          : true,
      )
      .slice(0, 10);
  }, [data.articles?.by_source, data.sources, sourceView, sourceQuery]);

  const stats: Array<{
    label: string;
    value: string;
    sub: string;
    href: string;
    icon: React.ElementType;
  }> = [
    {
      label: "Haberler",
      value: loading ? "…" : (data.articles?.total ?? 0).toLocaleString("tr-TR"),
      sub: `${data.articles?.by_status.find((s) => s.status === "cleaned")?.count ?? 0} hazır · ${
        data.articles?.embedded_count ?? 0
      } embed'lendi`,
      href: "/admin/articles",
      icon: FileText,
    },
    {
      label: "Kaynaklar",
      value: loading ? "…" : `${activeSources}/${totalSources}`,
      sub: `${activeSources} aktif · ${totalSources - activeSources} pasif`,
      href: "/admin/sources",
      icon: Database,
    },
    {
      label: "Kullanıcılar",
      value: loading ? "…" : (data.users?.total ?? 0).toLocaleString("tr-TR"),
      sub: `${data.users?.active ?? 0} aktif · ${data.users?.email_verified ?? 0} doğrulanmış`,
      href: "/admin/users",
      icon: Users,
    },
    {
      label: "Kuyruk",
      value: loading ? "…" : String(queuedJobs + runningJobs),
      sub: `${queuedJobs} sırada · ${runningJobs} çalışıyor${
        failedUnresolved > 0 ? ` · ${failedUnresolved} DLQ` : ""
      }`,
      href: "/admin/queue",
      icon: ServerCog,
    },
  ];

  return (
    <div className="space-y-6">
      {/* Critical alerts — sayfanın en üstü */}
      {(failedUnresolved > 0 || data.openTakedowns > 0) && (
        <div className="space-y-3">
          {failedUnresolved > 0 && (
            <Alert>
              <AlertTriangle />
              <AlertTitle>{failedUnresolved} çözülmemiş başarısız iş</AlertTitle>
              <AlertDescription>
                DLQ'da retry veya kapat bekliyor.
              </AlertDescription>
              <AlertAction>
                <Button asChild size="sm" variant="outline">
                  <Link href="/admin/queue">İncele</Link>
                </Button>
              </AlertAction>
            </Alert>
          )}
          {data.openTakedowns > 0 && (
            <Alert variant="destructive">
              <Scale />
              <AlertTitle>{data.openTakedowns} açık yasal talep</AlertTitle>
              <AlertDescription>
                24 saat SLA — submitted / triaging / investigating
              </AlertDescription>
              <AlertAction>
                <Button asChild size="sm" variant="outline">
                  <Link href="/admin/legal">Triage</Link>
                </Button>
              </AlertAction>
            </Alert>
          )}
        </div>
      )}

      {/* Hourly chart cards — son 6 saat */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {loading || !data.hourly ? (
          <>
            <DashboardStatCardSkeleton />
            <DashboardStatCardSkeleton />
            <DashboardStatCardSkeleton />
          </>
        ) : (
          <>
            <DashboardStatCard
              title="Yeni haberler"
              unitLabel="haber"
              hint="RSS / DOM kaynaklarından çekilen yeni makaleler. articles.fetched_at saatine göre gruplanır."
              data={data.hourly.articles}
            />
            <DashboardStatCard
              title="Temizlenen içerikler"
              unitLabel="haber"
              hint="Pipeline'i tamamlayıp 'cleaned' durumuna geçen makaleler. articles.updated_at saatine göre."
              data={data.hourly.jobs}
            />
            <DashboardStatCard
              title="İçerik üretimi"
              unitLabel="üretim"
              hint="Kullanıcıların oluşturduğu X / sosyal medya içerik üretimleri. generations.created_at saatine göre."
              data={data.hourly.generations}
            />
          </>
        )}
      </div>

      {loading || llmRange === null ? (
        <DashboardAreaChartCardSkeleton />
      ) : (
        <DashboardAreaChartCard
          title="LLM çağrısı"
          unitLabel="çağrı"
          series={llmRange.series}
          bucket={llmRange.bucket}
          labelMap={providerLabels}
          highlightKey="deepseek_v3"
          hint="DeepSeek / NVIDIA NIM / Claude gibi sağlayıcılara giden tüm chat / embed / rerank istekleri. Tooltip'teki model adları Sistem Ayarları'ndaki llm.* anahtarlarından okunur — değiştirdiğinde yansır."
          rangeOptions={[
            { value: "7d", label: "Son 7 gün" },
            { value: "30d", label: "Son 30 gün" },
            { value: "3m", label: "Son 3 ay" },
          ]}
          rangeValue={llmPeriod}
          onRangeChange={(v) => setLlmPeriod(v as ProviderCallsPeriod)}
        />
      )}

      {/* KPI cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map(({ label, value, sub, href, icon: Icon }) => (
          <Link key={label} href={href}>
            <Card className="h-full rounded-2xl shadow-none ring-[var(--border)] transition-colors hover:bg-muted hover:text-foreground dark:hover:bg-input/30">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardDescription>{label}</CardDescription>
                  <Icon className="size-4 text-muted-foreground" />
                </div>
                {loading ? (
                  <Skeleton className="mt-1 h-9 w-20" />
                ) : (
                  <CardTitle className="text-3xl tabular-nums">{value}</CardTitle>
                )}
              </CardHeader>
              <CardContent>
                {loading ? (
                  <Skeleton className="h-3 w-32" />
                ) : (
                  <p className="text-xs text-muted-foreground">{sub}</p>
                )}
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {/* Quick actions */}
      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader>
          <CardTitle className="text-base">Hızlı eylemler</CardTitle>
          <CardDescription>Sık kullanılan operasyonel görevler</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2 sm:grid-cols-3">
          <Button asChild variant="outline" className="justify-start">
            <Link href="/admin/sources/new">
              <Plus />
              Yeni RSS kaynak ekle
            </Link>
          </Button>
          <Button asChild variant="outline" className="justify-start">
            <Link href="/admin/queue">
              <ServerCog />
              DLQ kontrol
            </Link>
          </Button>
          <Button asChild variant="outline" className="justify-start">
            <Link href="/admin/legal">
              <Scale />
              Yasal talep triage
            </Link>
          </Button>
        </CardContent>
      </Card>

      {/* Top sources */}
      {loading ? (
        <Card className="rounded-2xl shadow-none ring-[var(--border)]">
          <CardHeader>
            <Skeleton className="h-5 w-64" />
            <Skeleton className="h-4 w-96" />
            <div className="mt-4 flex items-center justify-between gap-3">
              <Skeleton className="h-9 w-full max-w-sm rounded-3xl" />
              <Skeleton className="h-9 w-32 rounded-3xl" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {[0, 1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 rounded-2xl bg-muted/50 px-3 py-3"
                >
                  <Skeleton className="size-12 rounded-lg" />
                  <div className="flex-1 space-y-1.5">
                    <Skeleton className="h-4 w-40" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                  <Skeleton className="h-5 w-12" />
                  <div className="flex flex-col items-end gap-1">
                    <Skeleton className="h-3 w-10" />
                    <Skeleton className="h-4 w-12" />
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 flex justify-start">
              <Skeleton className="h-8 w-28" />
            </div>
          </CardContent>
        </Card>
      ) : data.articles && data.articles.by_source.length > 0 && (
        <Card className="rounded-2xl shadow-none ring-[var(--border)]">
          <CardHeader>
            <CardTitle className="text-base">
              En çok haber üreten kaynaklar
            </CardTitle>
            <CardDescription>
              Toplam haber sayısına göre top 10 kaynak. RSS / DOM ile filtrele,
              ad / slug / kategori ara.
            </CardDescription>
            <div className="mt-4 flex items-center justify-between gap-3">
              <InputGroup className="max-w-sm">
                <InputGroupAddon align="inline-start">
                  <Search />
                </InputGroupAddon>
                <InputGroupInput
                  placeholder="Kaynak veya kategori ara…"
                  value={sourceQuery}
                  onChange={(e) => setSourceQuery(e.target.value)}
                />
              </InputGroup>
              <ToggleGroup
                type="single"
                value={sourceView}
                onValueChange={(v) => v && setSourceView(v as SourceView)}
                variant="outline"
              >
                <ToggleGroupItem value="rss">RSS</ToggleGroupItem>
                <ToggleGroupItem value="dom" disabled>
                  DOM
                </ToggleGroupItem>
              </ToggleGroup>
            </div>
          </CardHeader>
          <CardContent>
            {topSources.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                Bu görünümde kaynak yok.
              </p>
            ) : (
              <ItemGroup>
                {topSources.map((s) => (
                  <Item key={s.slug} variant="muted" asChild>
                    <Link href={`/admin/sources?q=${encodeURIComponent(s.slug)}`}>
                      <ItemMedia>
                        <div className="flex size-12 items-center justify-center overflow-hidden rounded-lg border bg-background">
                          {s.domain ? (
                            <img
                              alt=""
                              src={`https://www.google.com/s2/favicons?domain=${s.domain}&sz=64`}
                              className="size-7"
                              loading="lazy"
                            />
                          ) : (
                            <span className="text-sm font-semibold">
                              {s.slug.slice(0, 2).toUpperCase()}
                            </span>
                          )}
                        </div>
                      </ItemMedia>
                      <ItemContent>
                        <ItemTitle>{s.name}</ItemTitle>
                        <ItemDescription>
                          {s.category ?? "kategori yok"}
                        </ItemDescription>
                      </ItemContent>
                      <div className="flex shrink-0 items-center gap-6">
                        <Badge variant="outline">
                          {SOURCE_TYPE_LABEL[s.type] ?? s.type}
                        </Badge>
                        <div className="flex flex-col items-end gap-0.5">
                          <span className="text-xs uppercase tracking-wider text-muted-foreground">
                            Haber
                          </span>
                          <span className="font-medium tabular-nums">
                            {s.count.toLocaleString("tr-TR")}
                          </span>
                        </div>
                      </div>
                    </Link>
                  </Item>
                ))}
              </ItemGroup>
            )}
            <div className="mt-3 flex justify-start">
              <Button asChild variant="ghost" size="sm">
                <Link href="/admin/sources">
                  Tümünü gör
                  <ArrowRight />
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
