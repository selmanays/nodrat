"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  RotateCcw,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
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
  getQueueOverview,
  listFailedJobs,
  resolveFailedJob,
  retryFailedJob,
  type FailedJobPublic,
  type QueueOverviewResponse,
} from "@/lib/api";

export default function AdminQueuePage() {
  const [overview, setOverview] = useState<QueueOverviewResponse | null>(null);
  const [failed, setFailed] = useState<FailedJobPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [unresolvedOnly, setUnresolvedOnly] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [ov, list] = await Promise.all([
        getQueueOverview(),
        listFailedJobs({ unresolved_only: unresolvedOnly, limit: 50 }),
      ]);
      setOverview(ov);
      setFailed(list.data);
    } catch (err) {
      toast.error((err as ApiException).message || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unresolvedOnly]);

  async function handleRetry(id: string) {
    if (!confirm("Bu başarısız işi tekrar denemek istediğinden emin misin?"))
      return;
    try {
      const result = await retryFailedJob(id);
      toast.success(`Yeniden kuyruğa alındı: ${result.new_job_id.slice(0, 8)}…`);
      await load();
    } catch (err) {
      toast.error((err as ApiException).message || "Retry başarısız");
    }
  }

  async function handleResolve(id: string) {
    const note = window.prompt("Kapanış notu (opsiyonel):");
    try {
      await resolveFailedJob(id, note || undefined);
      toast.success("Kapatıldı");
      await load();
    } catch (err) {
      toast.error((err as ApiException).message || "Kapatma başarısız");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Kuyruk</h1>
          <p className="text-sm text-muted-foreground">
            Worker durumu + DLQ (failed jobs)
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void load()}
          disabled={loading}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Yenile
        </Button>
      </div>

      {/* Queue overview */}
      {overview && (
        <>
          {overview.failed_jobs_unresolved > 0 && (
            <Card className="border-amber-200 bg-amber-50 dark:bg-amber-950/30">
              <CardContent className="flex items-start gap-3 py-3 text-sm">
                <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-medium text-amber-900 dark:text-amber-100">
                    {overview.failed_jobs_unresolved} çözülmemiş başarısız iş
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Aşağıdan inceleyip retry veya kapat.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            {overview.queues.map((q) => (
              <Card key={q.name}>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-mono">{q.name}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1.5 pt-0 text-xs">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Sırada</span>
                    <span className="font-mono">{q.queued_count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Çalışıyor</span>
                    <span className="font-mono">{q.running_count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">24s başarılı</span>
                    <span className="font-mono text-emerald-700">
                      {q.succeeded_count_24h}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">24s başarısız</span>
                    <span
                      className={`font-mono ${
                        q.failed_count_24h > 0 ? "text-red-700" : ""
                      }`}
                    >
                      {q.failed_count_24h}
                    </span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}

      {/* Failed jobs (DLQ) */}
      <Card>
        <CardHeader>
          <CardTitle>DLQ — Başarısız işler</CardTitle>
          <CardDescription>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={unresolvedOnly}
                onChange={(e) => setUnresolvedOnly(e.target.checked)}
              />
              Sadece çözülmemiş
            </label>
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              Yükleniyor…
            </p>
          ) : failed.length === 0 ? (
            <div className="text-center py-8 text-sm text-muted-foreground">
              <CheckCircle className="h-8 w-8 mx-auto mb-2 text-emerald-500" />
              {unresolvedOnly
                ? "Çözülmemiş başarısız iş yok 👍"
                : "Hiç başarısız iş yok"}
            </div>
          ) : (
            <div className="space-y-3">
              {failed.map((j) => (
                <Card key={j.id}>
                  <CardContent className="space-y-2 py-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge variant="outline" className="font-mono text-xs">
                            {j.job_type}
                          </Badge>
                          {j.resolved_at ? (
                            <Badge variant="success">Kapalı</Badge>
                          ) : (
                            <Badge variant="error">Açık</Badge>
                          )}
                          {j.retry_count > 0 && (
                            <span className="text-xs text-muted-foreground">
                              {j.retry_count}x retry
                            </span>
                          )}
                        </div>
                        {j.article_url && (
                          <div className="mt-1 text-xs text-muted-foreground truncate">
                            {j.article_url}
                          </div>
                        )}
                        <div className="mt-2 rounded-md bg-red-50 dark:bg-red-950/30 p-2 text-xs font-mono text-red-900 dark:text-red-100 break-all">
                          {j.error_message}
                        </div>
                        <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                          <span>
                            Son deneme:{" "}
                            {new Date(j.last_attempt_at).toLocaleString("tr-TR", {
                              day: "2-digit",
                              month: "short",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                          {j.resolved_at && (
                            <span>
                              Kapatıldı:{" "}
                              {new Date(j.resolved_at).toLocaleString("tr-TR", {
                                day: "2-digit",
                                month: "short",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </span>
                          )}
                        </div>
                        {j.resolution_note && (
                          <div className="mt-2 text-xs italic text-muted-foreground">
                            Not: {j.resolution_note}
                          </div>
                        )}
                      </div>
                      {!j.resolved_at && (
                        <div className="flex flex-col gap-1.5 flex-shrink-0">
                          <Button
                            size="sm"
                            variant="accent"
                            onClick={() => handleRetry(j.id)}
                          >
                            <RotateCcw className="h-3 w-3" />
                            Retry
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleResolve(j.id)}
                          >
                            <XCircle className="h-3 w-3" />
                            Kapat
                          </Button>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
