"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Database,
  FileText,
  Plus,
  Scale,
  ServerCog,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
      // Parallel fetch — bağımsız endpoint'ler
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

      // Settled sonuçlar — birinin hatası diğerlerini bozmaz
      const openTakedowns =
        (submitted.status === "fulfilled" ? submitted.value.total : 0) +
        (triaging.status === "fulfilled" ? triaging.value.total : 0) +
        (investigating.status === "fulfilled" ? investigating.value.total : 0);

      setData({
        articles: articles.status === "fulfilled" ? articles.value : null,
        users: users.status === "fulfilled" ? users.value : null,
        queue: queue.status === "fulfilled" ? queue.value : null,
        sources:
          sourcesList.status === "fulfilled" ? sourcesList.value.data : [],
        openTakedowns,
      });
    } catch (err) {
      toast.error((err as ApiException).message || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  const activeSources = data.sources.filter((s) => s.is_active).length;
  const totalSources = data.sources.length;
  const queuedJobs = data.queue?.queues.reduce((sum, q) => sum + q.queued_count, 0) ?? 0;
  const runningJobs =
    data.queue?.queues.reduce((sum, q) => sum + q.running_count, 0) ?? 0;
  const failedUnresolved = data.queue?.failed_jobs_unresolved ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Özet</h1>
        <p className="text-sm text-muted-foreground">
          Nodrat admin — sistem durumu, kuyruk ve içerik özeti
        </p>
      </div>

      {/* Critical alerts */}
      {(failedUnresolved > 0 || data.openTakedowns > 0) && (
        <div className="space-y-2">
          {failedUnresolved > 0 && (
            <Card className="border-amber-200 bg-amber-50 dark:bg-amber-950/30">
              <CardContent className="flex items-center justify-between gap-3 py-3 text-sm">
                <div className="flex items-center gap-3">
                  <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0" />
                  <div>
                    <p className="font-medium text-amber-900 dark:text-amber-100">
                      {failedUnresolved} çözülmemiş başarısız iş
                    </p>
                    <p className="text-xs text-muted-foreground">
                      DLQ'da retry veya kapat bekliyor.
                    </p>
                  </div>
                </div>
                <Link href="/admin/queue">
                  <Button size="sm" variant="outline">
                    İncele
                  </Button>
                </Link>
              </CardContent>
            </Card>
          )}
          {data.openTakedowns > 0 && (
            <Card className="border-rose-200 bg-rose-50 dark:bg-rose-950/30">
              <CardContent className="flex items-center justify-between gap-3 py-3 text-sm">
                <div className="flex items-center gap-3">
                  <Scale className="h-5 w-5 text-rose-600 flex-shrink-0" />
                  <div>
                    <p className="font-medium text-rose-900 dark:text-rose-100">
                      {data.openTakedowns} açık yasal talep
                    </p>
                    <p className="text-xs text-muted-foreground">
                      24 saat SLA — submitted / triaging / investigating
                    </p>
                  </div>
                </div>
                <Link href="/admin/legal">
                  <Button size="sm" variant="outline">
                    Triage
                  </Button>
                </Link>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Big stat cards */}
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        <Link href="/admin/articles" className="group">
          <Card className="h-full transition-colors group-hover:border-brand-300">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Haberler
              </CardTitle>
              <FileText className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold font-mono">
                {loading ? "…" : (data.articles?.total ?? 0).toLocaleString("tr-TR")}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {data.articles?.by_status.find((s) => s.status === "ready")?.count ?? 0}{" "}
                hazır ·{" "}
                {data.articles?.by_status.find((s) => s.status === "embedded")?.count ?? 0}{" "}
                embed'lendi
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/admin/sources" className="group">
          <Card className="h-full transition-colors group-hover:border-brand-300">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Kaynaklar
              </CardTitle>
              <Database className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold font-mono">
                {loading ? "…" : `${activeSources}/${totalSources}`}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {activeSources} aktif · {totalSources - activeSources} pasif
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/admin/users" className="group">
          <Card className="h-full transition-colors group-hover:border-brand-300">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Kullanıcılar
              </CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold font-mono">
                {loading ? "…" : (data.users?.total ?? 0).toLocaleString("tr-TR")}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {data.users?.active ?? 0} aktif · {data.users?.email_verified ?? 0} doğrulanmış
              </p>
            </CardContent>
          </Card>
        </Link>

        <Link href="/admin/queue" className="group">
          <Card className="h-full transition-colors group-hover:border-brand-300">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Kuyruk
              </CardTitle>
              <ServerCog className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold font-mono">
                {loading ? "…" : queuedJobs + runningJobs}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {queuedJobs} sırada · {runningJobs} çalışıyor
                {failedUnresolved > 0 && (
                  <>
                    {" · "}
                    <span className="text-amber-600 font-medium">
                      {failedUnresolved} DLQ
                    </span>
                  </>
                )}
              </p>
            </CardContent>
          </Card>
        </Link>
      </div>

      {/* Quick actions */}
      <Card>
        <CardHeader>
          <CardTitle>Hızlı eylemler</CardTitle>
          <CardDescription>Sık kullanılan operasyonel görevler</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-3">
            <Link href="/admin/sources/new">
              <Button variant="outline" size="sm" className="w-full justify-start">
                <Plus className="h-4 w-4" />
                Yeni RSS kaynak ekle
              </Button>
            </Link>
            <Link href="/admin/queue">
              <Button variant="outline" size="sm" className="w-full justify-start">
                <ServerCog className="h-4 w-4" />
                DLQ kontrol
              </Button>
            </Link>
            <Link href="/admin/legal">
              <Button variant="outline" size="sm" className="w-full justify-start">
                <Scale className="h-4 w-4" />
                Yasal talep triage
              </Button>
            </Link>
          </div>
        </CardContent>
      </Card>

      {/* Top sources by article count */}
      {data.articles && data.articles.by_source.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>En çok haber üreten kaynaklar</CardTitle>
            <CardDescription>Top 10 (toplam haber sayısı)</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              {data.articles.by_source.slice(0, 10).map((s) => (
                <div
                  key={s.slug}
                  className="flex items-center justify-between text-sm border-b last:border-0 py-1.5"
                >
                  <span className="font-medium">{s.name}</span>
                  <span className="font-mono text-muted-foreground">
                    {s.count.toLocaleString("tr-TR")}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
