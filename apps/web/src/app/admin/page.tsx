"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Database,
  FileText,
  Plus,
  Scale,
  ServerCog,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import {
  ApiException,
  articleStats,
  getAdminUserStats,
  getQueueOverview,
  listSources,
  listTakedownRequests,
  type AdminUserStatsResponse,
  type ArticleStatsResponse,
  type QueueOverviewResponse,
  type SourcePublic,
} from "@/lib/api";

interface DashboardData {
  articles: ArticleStatsResponse | null;
  users: AdminUserStatsResponse | null;
  queue: QueueOverviewResponse | null;
  sources: SourcePublic[];
  openTakedowns: number;
}

export default function AdminLandingPage() {
  const [data, setData] = useState<DashboardData>({
    articles: null,
    users: null,
    queue: null,
    sources: [],
    openTakedowns: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void loadAll();
  }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [articles, users, queue, sourcesList, submitted, triaging, investigating] =
        await Promise.allSettled([
          articleStats(),
          getAdminUserStats(),
          getQueueOverview(),
          listSources({ limit: 200 }),
          listTakedownRequests({ status: "submitted", limit: 1 }),
          listTakedownRequests({ status: "triaging", limit: 1 }),
          listTakedownRequests({ status: "investigating", limit: 1 }),
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
      sub: `${data.articles?.by_status.find((s) => s.status === "ready")?.count ?? 0} hazır · ${
        data.articles?.by_status.find((s) => s.status === "embedded")?.count ?? 0
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
      {/* Header */}
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Özet</h1>
        <p className="text-sm text-muted-foreground">
          Sistem durumu, kuyruk ve içerik özeti.
        </p>
      </div>

      {/* Critical alerts */}
      {(failedUnresolved > 0 || data.openTakedowns > 0) && (
        <div className="space-y-3">
          {failedUnresolved > 0 && (
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>{failedUnresolved} çözülmemiş başarısız iş</AlertTitle>
              <AlertDescription className="flex items-center justify-between gap-4">
                <span>DLQ'da retry veya kapat bekliyor.</span>
                <Button asChild size="sm" variant="outline">
                  <Link href="/admin/queue">İncele</Link>
                </Button>
              </AlertDescription>
            </Alert>
          )}
          {data.openTakedowns > 0 && (
            <Alert variant="destructive">
              <Scale className="h-4 w-4" />
              <AlertTitle>{data.openTakedowns} açık yasal talep</AlertTitle>
              <AlertDescription className="flex items-center justify-between gap-4">
                <span>24 saat SLA — submitted / triaging / investigating</span>
                <Button asChild size="sm" variant="outline">
                  <Link href="/admin/legal">Triage</Link>
                </Button>
              </AlertDescription>
            </Alert>
          )}
        </div>
      )}

      {/* KPI cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map(({ label, value, sub, href, icon: Icon }) => (
          <Link key={label} href={href} className="group">
            <Card className="h-full transition-colors hover:border-foreground/20">
              <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
                <CardDescription className="text-xs font-medium uppercase tracking-wide">
                  {label}
                </CardDescription>
                <Icon className="size-4 text-muted-foreground" />
              </CardHeader>
              <CardContent className="space-y-1">
                <div className="font-mono text-3xl font-semibold tabular-nums">
                  {value}
                </div>
                <p className="text-xs text-muted-foreground">{sub}</p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {/* Quick actions */}
      <Card>
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
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              En çok haber üreten kaynaklar
            </CardTitle>
            <CardDescription>Top 10 (toplam haber sayısı)</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {data.articles.by_source.slice(0, 10).map((s) => (
                <li
                  key={s.slug}
                  className="flex items-center justify-between py-2 text-sm"
                >
                  <span className="truncate font-medium">{s.name}</span>
                  <span className="font-mono text-muted-foreground tabular-nums">
                    {s.count.toLocaleString("tr-TR")}
                  </span>
                </li>
              ))}
            </ul>
            <Separator className="mt-4" />
            <div className="mt-3 flex justify-end">
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
