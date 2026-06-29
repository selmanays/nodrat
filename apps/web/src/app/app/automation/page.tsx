"use client";

/**
 * /app/automation — "Otomasyon Stüdyosu" (Faz 5.3b, vizyon merdiveninin tepesi).
 *
 * Kullanıcı abone olduğu kümeye KURAL koyar: küme "patlayınca" (breaking) otomatik
 * kaynaklı içerik üretilir → ONAY KUYRUĞUna düşer → kullanıcı onaylar/reddeder.
 * İki sekme: Kurallarım (kur/duraklat/sil) + Onay Kuyruğu (onayla/reddet).
 *
 * Çift flag-gate (automation.enabled + automation.studio.enabled). Flag OFF → API 403
 * → "henüz aktif değil" durumu. Onay semantiği: onayla → artefakt küme feed'inde görünür.
 */

import { useCallback, useEffect, useState } from "react";
import { Bot, Check, Loader2, Pause, Play, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiException } from "@/lib/api";
import {
  type AutomationRule,
  type AutomationRun,
  approveAutomationRun,
  createAutomationRule,
  deleteAutomationRule,
  listAutomationRules,
  listAutomationRuns,
  rejectAutomationRun,
  updateAutomationRule,
} from "@/lib/api/automation";
import { type SubscribedCluster, listMyClusters } from "@/lib/api/clusters";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("tr-TR", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

export default function AutomationStudioPage() {
  const [loading, setLoading] = useState(true);
  const [disabled, setDisabled] = useState(false); // flag OFF → 403
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [clusters, setClusters] = useState<SubscribedCluster[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [newCluster, setNewCluster] = useState<string>("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, q, c] = await Promise.all([
        listAutomationRules(),
        listAutomationRuns(),
        listMyClusters().catch(() => ({ clusters: [], total: 0 })),
      ]);
      setRules(r.rules);
      setRuns(q.runs);
      setClusters(c.clusters);
      setDisabled(false);
    } catch (err) {
      if (err instanceof ApiException && err.status === 403) {
        setDisabled(true);
      } else {
        toast.error("Otomasyon verileri yüklenemedi.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Kuralı olmayan abone kümeler (yeni kural için seçilebilir)
  const ruledClusterIds = new Set(rules.map((r) => r.cluster_id));
  const availableClusters = clusters.filter((c) => !ruledClusterIds.has(c.cluster_id));

  async function handleCreate() {
    if (!newCluster) return;
    setBusy("create");
    try {
      await createAutomationRule({ cluster_id: newCluster });
      toast.success("Kural oluşturuldu.");
      setNewCluster("");
      await load();
    } catch (err) {
      if (err instanceof ApiException && err.status === 409) {
        toast.error("Bu küme için zaten bir kural var.");
      } else {
        toast.error("Kural oluşturulamadı.");
      }
    } finally {
      setBusy(null);
    }
  }

  async function handleToggle(rule: AutomationRule) {
    const next = rule.status === "active" ? "paused" : "active";
    setBusy(rule.rule_id);
    try {
      await updateAutomationRule(rule.rule_id, { status: next, enabled: next === "active" });
      toast.success(next === "active" ? "Kural sürdürüldü." : "Kural duraklatıldı.");
      await load();
    } catch {
      toast.error("Güncellenemedi.");
    } finally {
      setBusy(null);
    }
  }

  async function handleDelete(rule: AutomationRule) {
    setBusy(rule.rule_id);
    try {
      await deleteAutomationRule(rule.rule_id);
      toast.success("Kural silindi.");
      await load();
    } catch {
      toast.error("Silinemedi.");
    } finally {
      setBusy(null);
    }
  }

  async function handleReview(run: AutomationRun, approve: boolean) {
    setBusy(run.run_id);
    try {
      if (approve) {
        await approveAutomationRun(run.run_id);
        toast.success("Onaylandı — içerik kümede yayınlandı.");
      } else {
        await rejectAutomationRun(run.run_id);
        toast.success("Reddedildi.");
      }
      await load();
    } catch {
      toast.error("İşlem başarısız.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 p-4">
      <div className="flex items-center gap-3">
        <Bot className="size-6 text-primary" />
        <div>
          <h1 className="text-xl font-semibold">Otomasyon Stüdyosu</h1>
          <p className="text-sm text-muted-foreground">
            Abone olduğun küme gündeme gelince otomatik kaynaklı içerik üret → onayla → yayınla.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : disabled ? (
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            Otomasyon Stüdyosu henüz aktif değil. Yakında burada olacak.
          </CardContent>
        </Card>
      ) : (
        <Tabs defaultValue="rules">
          <TabsList>
            <TabsTrigger value="rules">Kurallarım ({rules.length})</TabsTrigger>
            <TabsTrigger value="queue">Onay Kuyruğu ({runs.length})</TabsTrigger>
          </TabsList>

          {/* ---- Kurallar ---- */}
          <TabsContent value="rules" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Yeni kural</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap items-center gap-3">
                <Select value={newCluster} onValueChange={setNewCluster}>
                  <SelectTrigger className="w-64">
                    <SelectValue placeholder="Abone küme seç…" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableClusters.length === 0 ? (
                      <div className="px-2 py-1.5 text-sm text-muted-foreground">
                        Uygun küme yok (önce bir kümeye abone ol)
                      </div>
                    ) : (
                      availableClusters.map((c) => (
                        <SelectItem key={c.cluster_id} value={c.cluster_id}>
                          {c.canonical_name}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
                <Button onClick={handleCreate} disabled={!newCluster || busy === "create"}>
                  {busy === "create" ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Plus className="size-4" />
                  )}
                  Kural ekle
                </Button>
                <span className="text-xs text-muted-foreground">
                  Tetik: küme “patlayınca” (breaking) · onay kuyruğu
                </span>
              </CardContent>
            </Card>

            {rules.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                Henüz kural yok. Bir kümeye kural ekleyerek başla.
              </p>
            ) : (
              rules.map((rule) => (
                <Card key={rule.rule_id}>
                  <CardContent className="flex items-center justify-between gap-3 py-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-medium">
                          {rule.cluster_name ?? "—"}
                        </span>
                        <Badge variant={rule.status === "active" ? "default" : "secondary"}>
                          {rule.status === "active" ? "Aktif" : "Duraklatıldı"}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Tetik: {rule.states.join(", ")} · Son: {fmtDate(rule.last_triggered_at)}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleToggle(rule)}
                        disabled={busy === rule.rule_id}
                      >
                        {rule.status === "active" ? (
                          <Pause className="size-4" />
                        ) : (
                          <Play className="size-4" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(rule)}
                        disabled={busy === rule.rule_id}
                      >
                        <Trash2 className="size-4 text-destructive" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </TabsContent>

          {/* ---- Onay kuyruğu ---- */}
          <TabsContent value="queue" className="space-y-4">
            {runs.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                Onay bekleyen içerik yok.
              </p>
            ) : (
              runs.map((run) => (
                <Card key={run.run_id}>
                  <CardContent className="space-y-3 py-4">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{run.cluster_name ?? "—"}</span>
                      <span className="text-xs text-muted-foreground">
                        {fmtDate(run.triggered_at)}
                      </span>
                    </div>
                    <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                      {run.artifact_preview ?? "(önizleme yok)"}
                    </p>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        onClick={() => handleReview(run, true)}
                        disabled={busy === run.run_id}
                      >
                        <Check className="size-4" />
                        Onayla
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleReview(run, false)}
                        disabled={busy === run.run_id}
                      >
                        <X className="size-4" />
                        Reddet
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
