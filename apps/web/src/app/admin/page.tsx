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
  articleStats,
  dashboardHourly,
  getAdminUserStats,
  getQueueOverview,
  listSources,
  listTakedownRequests,
  type AdminUserStatsResponse,
  type ArticleStatsResponse,
  type DashboardHourlyResponse,
  type QueueOverviewResponse,
  type SourcePublic,
} from "@/lib/api";
import { DashboardStatCard } from "@/components/blocks/dashboard-stat-card";

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
      {data.hourly && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <DashboardStatCard
            title="Yeni haberler"
            description="Son 6 saat / saatlik kırılım"
            data={data.hourly.articles}
          />
          <DashboardStatCard
            title="Tamamlanan işler"
            description="Succeeded + failed / saat"
            data={data.hourly.jobs}
          />
          <DashboardStatCard
            title="İçerik üretimi"
            description="Generations / saat"
            data={data.hourly.generations}
          />
          <DashboardStatCard
            title="LLM çağrısı"
            description="Provider call logs / saat"
            data={data.hourly.provider_calls}
          />
        </div>
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
                <CardTitle className="text-3xl tabular-nums">{value}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">{sub}</p>
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
      {data.articles && data.articles.by_source.length > 0 && (
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
