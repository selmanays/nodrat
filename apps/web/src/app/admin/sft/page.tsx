"use client";

/**
 * Admin SFT data pipeline dashboard (#569).
 *
 * Backend: apps/api/app/api/admin_sft.py — 5 endpoint.
 * Lib: apps/web/src/lib/admin-sft-api.ts.
 *
 * Görüntüler:
 *   - 4 Card: total_samples, eligible_pending, opted_in_users, daily rate
 *   - LineChart: daily curated time series (30 gün)
 *   - 2 Table: by_split + excluded_breakdown
 *   - Recent table (preview, son 50)
 *   - Export Dialog (task_type + split + format) → JSONL download
 *   - Recompute eligibility button
 *
 * Auth: super_admin role only (backend enforce eder, 403 fallback).
 */

import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import { Download, Loader2, Play, RefreshCw, RotateCcw, Save } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/blocks/page-header";
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ApiException,
  adminSettingsList,
  adminSettingReset,
  adminSettingUpdate,
  type AdminSettingItem,
} from "@/lib/api";
import {
  downloadSFTExport,
  getSFTConsentStats,
  getSFTRecent,
  getSFTStats,
  recomputeSFTEligibility,
  triggerSFTRun,
  type SFTConsentStats,
  type SFTRecentSample,
  type SFTStatsResponse,
} from "@/lib/admin-sft-api";
import { formatTrDate, formatTrDateTime } from "@/lib/format";

const EXCLUDED_LABEL: Record<string, string> = {
  no_consent: "Onay yok",
  consent_revoked: "Onay geri çekildi",
  wrong_action: "Yanlış action",
  edit_too_large: "Edit çok büyük",
  halu_flagged: "Halü flag'li",
  review_buffer: "7g bekleme",
  pii_secondary_hit: "PII tespit edildi",
  wrong_status: "Status uygun değil",
};

const TASK_TYPE_OPTIONS = [
  { value: "research_answer", label: "Research Answer (yeni)" },
  { value: "content_generator", label: "Content Generator (legacy)" },
  { value: "query_planner", label: "Query Planner" },
  { value: "style_analyzer", label: "Style Analyzer" },
];

const SAMPLE_TYPE_LABEL: Record<string, string> = {
  sft: "SFT",
  dpo_chosen: "DPO Chosen",
  dpo_rejected: "DPO Rejected",
};

const SPLIT_OPTIONS = [
  { value: "all", label: "Tüm split'ler" },
  { value: "train", label: "Train (~80%)" },
  { value: "val", label: "Val (~10%)" },
  { value: "test", label: "Test (~10%)" },
];

interface SftSettingsState {
  enabled: AdminSettingItem | null;
  reviewBufferDays: AdminSettingItem | null;
  dailyMaxSamples: AdminSettingItem | null;
  minQualityScore: AdminSettingItem | null;
}

const SFT_SETTING_KEYS = {
  enabled: "sft.curator.enabled",
  reviewBufferDays: "sft.curator.review_buffer_days",
  dailyMaxSamples: "sft.curator.daily_max_samples",
  minQualityScore: "sft.curator.min_quality_score",
} as const;

export default function AdminSftPage() {
  const [stats, setStats] = useState<SFTStatsResponse | null>(null);
  const [consent, setConsent] = useState<SFTConsentStats | null>(null);
  const [recent, setRecent] = useState<SFTRecentSample[]>([]);
  const [loading, setLoading] = useState(true);
  const [recomputing, setRecomputing] = useState(false);

  // Export modal state
  const [exportOpen, setExportOpen] = useState(false);
  const [exportTaskType, setExportTaskType] = useState("research_answer");
  const [exportSplit, setExportSplit] = useState("all");
  const [exporting, setExporting] = useState(false);

  // Pipeline ayarları state
  const [settings, setSettings] = useState<SftSettingsState>({
    enabled: null,
    reviewBufferDays: null,
    dailyMaxSamples: null,
    minQualityScore: null,
  });
  const [reviewBufferInput, setReviewBufferInput] = useState("");
  const [dailyMaxInput, setDailyMaxInput] = useState("");
  const [minQualityInput, setMinQualityInput] = useState("");
  const [savingSetting, setSavingSetting] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);

  useEffect(() => {
    void loadAll();
  }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [s, c, r, settingsResp] = await Promise.all([
        getSFTStats(30),
        getSFTConsentStats(),
        getSFTRecent(50),
        adminSettingsList("sft").catch((err) => {
          if (typeof console !== "undefined") {
            console.warn("sft settings fetch failed:", err);
          }
          return null;
        }),
      ]);
      setStats(s);
      setConsent(c);
      setRecent(r);

      if (settingsResp) {
        const byKey: Record<string, AdminSettingItem> = {};
        for (const item of settingsResp.data) {
          byKey[item.key] = item;
        }
        const newSettings: SftSettingsState = {
          enabled: byKey[SFT_SETTING_KEYS.enabled] ?? null,
          reviewBufferDays: byKey[SFT_SETTING_KEYS.reviewBufferDays] ?? null,
          dailyMaxSamples: byKey[SFT_SETTING_KEYS.dailyMaxSamples] ?? null,
          minQualityScore: byKey[SFT_SETTING_KEYS.minQualityScore] ?? null,
        };
        setSettings(newSettings);
        if (newSettings.reviewBufferDays) {
          setReviewBufferInput(String(newSettings.reviewBufferDays.value));
        }
        if (newSettings.dailyMaxSamples) {
          setDailyMaxInput(String(newSettings.dailyMaxSamples.value));
        }
        if (newSettings.minQualityScore) {
          setMinQualityInput(String(newSettings.minQualityScore.value));
        }
      }
    } catch (err) {
      toast.error((err as ApiException).message || "SFT verileri yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  async function handleToggleEnabled(checked: boolean) {
    setSavingSetting(SFT_SETTING_KEYS.enabled);
    try {
      const updated = await adminSettingUpdate(SFT_SETTING_KEYS.enabled, checked);
      setSettings((prev) => ({ ...prev, enabled: updated }));
      toast.success(
        checked
          ? "SFT curator etkinleştirildi — gece 02:45 UTC çalışmaya başlayacak"
          : "SFT curator durduruldu (kill switch)",
      );
    } catch (err) {
      toast.error((err as ApiException).message || "Güncellenemedi");
    } finally {
      setSavingSetting(null);
    }
  }

  async function handleSaveNumberSetting(
    key: string,
    raw: string,
    parser: (s: string) => number,
    field: keyof SftSettingsState,
    label: string,
  ) {
    const parsed = parser(raw);
    if (Number.isNaN(parsed)) {
      toast.error(`Geçersiz ${label}`);
      return;
    }
    setSavingSetting(key);
    try {
      const updated = await adminSettingUpdate(key, parsed);
      setSettings((prev) => ({ ...prev, [field]: updated }));
      toast.success(`${label} güncellendi: ${parsed}`);
    } catch (err) {
      toast.error((err as ApiException).message || "Güncellenemedi");
    } finally {
      setSavingSetting(null);
    }
  }

  async function handleResetSetting(
    key: string,
    field: keyof SftSettingsState,
    inputSetter: ((s: string) => void) | null,
  ) {
    setSavingSetting(key);
    try {
      const reset = await adminSettingReset(key);
      setSettings((prev) => ({ ...prev, [field]: reset }));
      if (inputSetter) inputSetter(String(reset.value));
      toast.success(`${key} default değere döndürüldü`);
    } catch (err) {
      toast.error((err as ApiException).message || "Sıfırlanamadı");
    } finally {
      setSavingSetting(null);
    }
  }

  async function handleRecompute() {
    setRecomputing(true);
    try {
      const resp = await recomputeSFTEligibility(30);
      toast.success(
        `Recompute tamam: ${resp.scanned} taraması, +${resp.became_eligible} eligible, -${resp.became_ineligible} ineligible`,
      );
      await loadAll();
    } catch (err) {
      toast.error((err as ApiException).message || "Recompute başarısız");
    } finally {
      setRecomputing(false);
    }
  }

  async function handleTriggerRun() {
    if (!settings.enabled?.value) {
      toast.error(
        "ETL worker kapalı (kill switch). Önce Pipeline Ayarları'ndan açın.",
      );
      return;
    }
    setTriggering(true);
    try {
      const resp = await triggerSFTRun();
      toast.success(
        `ETL kuyruğa alındı (task: ${resp.task_id.slice(0, 8)}…). Birkaç saniye sonra sayfayı yenileyin.`,
      );
      // 8 saniye sonra otomatik refresh — worker'ın iş bitirmesi için yeterli süre
      setTimeout(() => {
        void loadAll();
      }, 8000);
    } catch (err) {
      toast.error((err as ApiException).message || "Trigger başarısız");
    } finally {
      setTriggering(false);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      const resp = await downloadSFTExport({
        task_type: exportTaskType,
        sft_split: exportSplit === "all" ? null : exportSplit,
        format: "chatml",
        mark_exported: true,
      });
      toast.success(
        `İndirildi: ${resp.filename} (${(resp.size / 1024).toFixed(1)} KB)`,
      );
      setExportOpen(false);
      await loadAll();
    } catch (err) {
      toast.error((err as Error).message || "Export başarısız");
    } finally {
      setExporting(false);
    }
  }

  const optInRate =
    consent && consent.total_users > 0
      ? ((consent.opted_in / consent.total_users) * 100).toFixed(1)
      : "—";

  const dailyAvg =
    stats && stats.daily_curated.length > 0
      ? Math.round(
          stats.daily_curated.reduce((sum, p) => sum + p.count, 0) /
            stats.daily_curated.length,
        )
      : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="SFT Data Pipeline"
        description="Trendyol-LLM-7B-chat-v4.1.0 üzerine fine-tune için altın etiketli training dataset. Backend: training_samples + nightly Celery ETL (02:45 UTC). Kill switch: sft.curator.enabled."
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="default"
              size="sm"
              onClick={() => void handleTriggerRun()}
              disabled={triggering || !settings.enabled?.value}
              title={
                settings.enabled?.value
                  ? "Nightly schedule'ı beklemeden ETL'i şimdi çalıştır"
                  : "Önce Pipeline Ayarları'ndan ETL worker'ı açın"
              }
            >
              {triggering ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              Şimdi çalıştır
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={() => void handleRecompute()}
              disabled={recomputing}
            >
              {recomputing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Eligibility recompute
            </Button>

            <Dialog open={exportOpen} onOpenChange={setExportOpen}>
              <DialogTrigger asChild>
                <Button size="sm">
                  <Download className="h-4 w-4" />
                  JSONL export
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>SFT dataset export (ChatML)</DialogTitle>
                  <DialogDescription>
                    Hugging Face datasets.load_dataset() ile uyumlu JSONL.
                    Each sample: {"{messages, metadata}"}.
                  </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="export-task">Task type</Label>
                    <Select
                      value={exportTaskType}
                      onValueChange={setExportTaskType}
                    >
                      <SelectTrigger id="export-task">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {TASK_TYPE_OPTIONS.map((o) => (
                          <SelectItem key={o.value} value={o.value}>
                            {o.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="export-split">Split</Label>
                    <Select value={exportSplit} onValueChange={setExportSplit}>
                      <SelectTrigger id="export-split">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {SPLIT_OPTIONS.map((o) => (
                          <SelectItem key={o.value} value={o.value}>
                            {o.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <p className="text-xs text-muted-foreground">
                    Export sonrası exported_at = NOW() set edilir +
                    admin_audit_log entry. Manuel HF Hub push:{" "}
                    <code className="rounded bg-muted px-1">
                      apps/api/scripts/sft_push_hf.py
                    </code>
                  </p>
                </div>

                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setExportOpen(false)}
                    disabled={exporting}
                  >
                    İptal
                  </Button>
                  <Button onClick={() => void handleExport()} disabled={exporting}>
                    {exporting ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Download className="h-4 w-4" />
                    )}
                    İndir
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        }
      />

      {/* Pipeline Ayarları — admin tunable settings */}
      <Card>
        <CardHeader>
          <CardTitle>Pipeline ayarları</CardTitle>
          <CardDescription>
            sft.curator.* admin tunable. Değişiklikler Redis pub/sub ile
            ~30 saniye içinde tüm container'lara yansır.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Kill switch */}
          <div className="flex items-center justify-between gap-4 rounded-lg border p-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Label
                  htmlFor="sft-enabled"
                  className="text-base font-medium cursor-pointer"
                >
                  ETL worker (kill switch)
                </Label>
                {settings.enabled?.is_overridden && (
                  <Badge variant="outline" className="text-[10px]">
                    override
                  </Badge>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                Açıkken her gece 02:45 UTC&apos;de çalışır:
                messages.sft_eligible=true VEYA dpo_rejected=true → training_samples ETL.
                Kapalıyken hiçbir şey yapmaz.
              </p>
              <p className="text-xs text-muted-foreground">
                Default: <code className="rounded bg-muted px-1">false</code> —
                Mevcut: <code className="rounded bg-muted px-1">{String(settings.enabled?.value ?? "false")}</code>
              </p>
            </div>
            <Switch
              id="sft-enabled"
              checked={Boolean(settings.enabled?.value)}
              disabled={
                loading ||
                settings.enabled === null ||
                savingSetting === SFT_SETTING_KEYS.enabled
              }
              onCheckedChange={(c) => void handleToggleEnabled(c)}
            />
          </div>

          {/* Numeric inputs — review_buffer_days, daily_max_samples, min_quality_score */}
          <div className="grid gap-4 md:grid-cols-3">
            <NumericSettingInput
              id="sft-review-buffer"
              label="Review buffer (gün)"
              hint="Mesaj oluştuktan kaç gün sonra ETL'e dahil. Default: 7"
              defaultValue={String(settings.reviewBufferDays?.default ?? 7)}
              currentValue={
                settings.reviewBufferDays
                  ? String(settings.reviewBufferDays.value)
                  : ""
              }
              isOverridden={settings.reviewBufferDays?.is_overridden ?? false}
              inputValue={reviewBufferInput}
              onInputChange={setReviewBufferInput}
              saving={savingSetting === SFT_SETTING_KEYS.reviewBufferDays}
              disabled={loading || settings.reviewBufferDays === null}
              onSave={() =>
                void handleSaveNumberSetting(
                  SFT_SETTING_KEYS.reviewBufferDays,
                  reviewBufferInput,
                  (s) => parseInt(s, 10),
                  "reviewBufferDays",
                  "Review buffer",
                )
              }
              onReset={() =>
                void handleResetSetting(
                  SFT_SETTING_KEYS.reviewBufferDays,
                  "reviewBufferDays",
                  setReviewBufferInput,
                )
              }
            />

            <NumericSettingInput
              id="sft-daily-max"
              label="Günlük max sample"
              hint="Bir koşumda max sample (overflow protection). Default: 1000"
              defaultValue={String(settings.dailyMaxSamples?.default ?? 1000)}
              currentValue={
                settings.dailyMaxSamples
                  ? String(settings.dailyMaxSamples.value)
                  : ""
              }
              isOverridden={settings.dailyMaxSamples?.is_overridden ?? false}
              inputValue={dailyMaxInput}
              onInputChange={setDailyMaxInput}
              saving={savingSetting === SFT_SETTING_KEYS.dailyMaxSamples}
              disabled={loading || settings.dailyMaxSamples === null}
              onSave={() =>
                void handleSaveNumberSetting(
                  SFT_SETTING_KEYS.dailyMaxSamples,
                  dailyMaxInput,
                  (s) => parseInt(s, 10),
                  "dailyMaxSamples",
                  "Daily max samples",
                )
              }
              onReset={() =>
                void handleResetSetting(
                  SFT_SETTING_KEYS.dailyMaxSamples,
                  "dailyMaxSamples",
                  setDailyMaxInput,
                )
              }
            />

            <NumericSettingInput
              id="sft-min-quality"
              label="Min quality (0-1)"
              hint="Composite quality threshold. Default: 0.7"
              defaultValue={String(settings.minQualityScore?.default ?? 0.7)}
              currentValue={
                settings.minQualityScore
                  ? String(settings.minQualityScore.value)
                  : ""
              }
              isOverridden={settings.minQualityScore?.is_overridden ?? false}
              inputValue={minQualityInput}
              onInputChange={setMinQualityInput}
              saving={savingSetting === SFT_SETTING_KEYS.minQualityScore}
              disabled={loading || settings.minQualityScore === null}
              onSave={() =>
                void handleSaveNumberSetting(
                  SFT_SETTING_KEYS.minQualityScore,
                  minQualityInput,
                  parseFloat,
                  "minQualityScore",
                  "Min quality score",
                )
              }
              onReset={() =>
                void handleResetSetting(
                  SFT_SETTING_KEYS.minQualityScore,
                  "minQualityScore",
                  setMinQualityInput,
                )
              }
            />
          </div>
        </CardContent>
      </Card>

      {/* 4 Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <StatCard
          title="Toplam sample"
          value={loading ? null : stats?.total_samples ?? 0}
          hint="Curated training_samples row sayısı"
        />
        <StatCard
          title="Eligible (curate bekliyor)"
          value={loading ? null : stats?.eligible_pending ?? 0}
          hint="messages.sft_eligible=true OR dpo_rejected=true henüz training_samples'a girmemiş"
        />
        <StatCard
          title="Günlük ortalama (30g)"
          value={loading ? null : dailyAvg}
          hint="Son 30 gün curate edilen ortalama günlük sample"
        />
        <StatCard
          title="Consent opt-in oranı"
          value={loading ? null : `${optInRate}%`}
          hint={
            consent
              ? `${consent.opted_in} / ${consent.total_users} kullanıcı (${consent.opted_in_revoked} geri çekti)`
              : ""
          }
        />
      </div>

      {/* Daily curated chart */}
      <Card>
        <CardHeader>
          <CardTitle>Günlük curated sample (son 30 gün)</CardTitle>
          <CardDescription>
            Nightly ETL (02:45 UTC) çalışmasının günlük çıktısı.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-[200px] w-full" />
          ) : (stats?.daily_curated.length ?? 0) === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              Henüz veri yok. ETL ya kapalı (sft.curator.enabled=false) ya da
              eligible generation yok.
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={stats!.daily_curated}>
                <defs>
                  <linearGradient id="curatedGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" fontSize={11} />
                <YAxis fontSize={11} />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke="hsl(var(--primary))"
                  fill="url(#curatedGrad)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Distribution + Sample Type + Excluded — 3-col */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Split dağılımı</CardTitle>
            <CardDescription>
              Deterministic hash(message_id) % 100 — beklenen ~80/10/10.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-24 w-full" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Split</TableHead>
                    <TableHead className="text-right">Sample</TableHead>
                    <TableHead className="text-right">Oran</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(["train", "val", "test"] as const).map((split) => {
                    const count = stats?.by_split[split] ?? 0;
                    const total = stats?.total_samples ?? 0;
                    const ratio =
                      total > 0 ? ((count / total) * 100).toFixed(1) : "—";
                    return (
                      <TableRow key={split}>
                        <TableCell>{split}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {count.toLocaleString("tr-TR")}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {ratio}%
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Sample type</CardTitle>
            <CardDescription>
              SFT vs DPO (chosen + rejected) — research-derived sample dağılımı.
              {stats && stats.dpo_pair_complete > 0 && (
                <span className="mt-1 block text-xs">
                  DPO pair complete:{" "}
                  <span className="font-medium text-foreground">
                    {stats.dpo_pair_complete.toLocaleString("tr-TR")}
                  </span>
                </span>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-24 w-full" />
            ) : Object.keys(stats?.by_sample_type ?? {}).length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                Henüz veri yok.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tip</TableHead>
                    <TableHead className="text-right">Sample</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(["sft", "dpo_chosen", "dpo_rejected"] as const).map(
                    (st) => {
                      const count = stats?.by_sample_type[st] ?? 0;
                      return (
                        <TableRow key={st}>
                          <TableCell>
                            <Badge
                              variant={
                                st === "sft"
                                  ? "default"
                                  : st === "dpo_chosen"
                                    ? "secondary"
                                    : "destructive"
                              }
                            >
                              {SAMPLE_TYPE_LABEL[st]}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {count.toLocaleString("tr-TR")}
                          </TableCell>
                        </TableRow>
                      );
                    },
                  )}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Excluded breakdown</CardTitle>
            <CardDescription>
              sft_eligible=false satırların sebepleri (#566 7-koşullu kural).
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-32 w-full" />
            ) : Object.keys(stats?.excluded_breakdown ?? {}).length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                Excluded sebep yok.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Neden</TableHead>
                    <TableHead className="text-right">Sayı</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(stats?.excluded_breakdown ?? {})
                    .sort((a, b) => b[1] - a[1])
                    .map(([reason, count]) => (
                      <TableRow key={reason}>
                        <TableCell>
                          {EXCLUDED_LABEL[reason] ?? reason}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {count.toLocaleString("tr-TR")}
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent samples */}
      <Card>
        <CardHeader>
          <CardTitle>Son 50 curated sample</CardTitle>
          <CardDescription>
            Preview — input/output 240 char ile sansürlü.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-64 w-full" />
          ) : recent.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              Henüz curated sample yok.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Curate</TableHead>
                  <TableHead>Task</TableHead>
                  <TableHead>Tip</TableHead>
                  <TableHead>Split</TableHead>
                  <TableHead className="text-right">Edit dist</TableHead>
                  <TableHead className="text-right">Char</TableHead>
                  <TableHead>Input preview</TableHead>
                  <TableHead>Exported</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatTrDateTime(r.curated_at)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{r.task_type}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          r.sample_type === "sft"
                            ? "default"
                            : r.sample_type === "dpo_chosen"
                              ? "secondary"
                              : "destructive"
                        }
                      >
                        {SAMPLE_TYPE_LABEL[r.sample_type] ?? r.sample_type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          r.sft_split === "train"
                            ? "default"
                            : r.sft_split === "val"
                              ? "secondary"
                              : "outline"
                        }
                      >
                        {r.sft_split}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {r.edit_distance !== null
                        ? r.edit_distance.toFixed(3)
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {r.char_count ?? "—"}
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-xs">
                      {r.input_preview}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {r.exported_at ? formatTrDate(r.exported_at) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface StatCardProps {
  title: string;
  value: number | string | null;
  hint?: string;
}

function StatCard({ title, value, hint }: StatCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-3xl tabular-nums">
          {value === null ? <Skeleton className="h-8 w-20" /> : value.toLocaleString("tr-TR")}
        </CardTitle>
      </CardHeader>
      {hint && (
        <CardContent>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </CardContent>
      )}
    </Card>
  );
}

interface NumericSettingInputProps {
  id: string;
  label: string;
  hint: string;
  defaultValue: string;
  currentValue: string;
  isOverridden: boolean;
  inputValue: string;
  onInputChange: (value: string) => void;
  saving: boolean;
  disabled: boolean;
  onSave: () => void;
  onReset: () => void;
}

function NumericSettingInput({
  id,
  label,
  hint,
  defaultValue,
  currentValue,
  isOverridden,
  inputValue,
  onInputChange,
  saving,
  disabled,
  onSave,
  onReset,
}: NumericSettingInputProps) {
  const dirty = inputValue.trim() !== currentValue.trim();
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id} className="text-sm font-medium">
          {label}
        </Label>
        {isOverridden && (
          <Badge variant="outline" className="text-[10px]">
            override
          </Badge>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{hint}</p>
      <div className="flex items-center gap-2">
        <Input
          id={id}
          type="text"
          inputMode="decimal"
          value={inputValue}
          onChange={(e) => onInputChange(e.target.value)}
          disabled={disabled || saving}
          className="font-mono"
        />
        <Button
          size="sm"
          variant="default"
          onClick={onSave}
          disabled={disabled || saving || !dirty}
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onReset}
          disabled={disabled || saving || !isOverridden}
          title="Default değere döndür"
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
      </div>
      <p className="text-[10px] text-muted-foreground tabular-nums">
        default: {defaultValue} · mevcut: {currentValue || "—"}
      </p>
    </div>
  );
}
