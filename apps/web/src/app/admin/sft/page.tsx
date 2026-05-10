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
import { Download, Loader2, RefreshCw } from "lucide-react";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiException } from "@/lib/api";
import {
  downloadSFTExport,
  getSFTConsentStats,
  getSFTRecent,
  getSFTStats,
  recomputeSFTEligibility,
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
  { value: "content_generator", label: "Content Generator" },
  { value: "query_planner", label: "Query Planner" },
  { value: "style_analyzer", label: "Style Analyzer" },
];

const SPLIT_OPTIONS = [
  { value: "all", label: "Tüm split'ler" },
  { value: "train", label: "Train (~80%)" },
  { value: "val", label: "Val (~10%)" },
  { value: "test", label: "Test (~10%)" },
];

export default function AdminSftPage() {
  const [stats, setStats] = useState<SFTStatsResponse | null>(null);
  const [consent, setConsent] = useState<SFTConsentStats | null>(null);
  const [recent, setRecent] = useState<SFTRecentSample[]>([]);
  const [loading, setLoading] = useState(true);
  const [recomputing, setRecomputing] = useState(false);

  // Export modal state
  const [exportOpen, setExportOpen] = useState(false);
  const [exportTaskType, setExportTaskType] = useState("content_generator");
  const [exportSplit, setExportSplit] = useState("all");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    void loadAll();
  }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [s, c, r] = await Promise.all([
        getSFTStats(30),
        getSFTConsentStats(),
        getSFTRecent(50),
      ]);
      setStats(s);
      setConsent(c);
      setRecent(r);
    } catch (err) {
      toast.error((err as ApiException).message || "SFT verileri yüklenemedi");
    } finally {
      setLoading(false);
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
          <div className="flex items-center gap-2">
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
          hint="generations.sft_eligible=true henüz training_samples'a girmemiş"
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

      {/* Distribution + Excluded breakdown — yan yana */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Split dağılımı</CardTitle>
            <CardDescription>
              Deterministic hash(generation_id) % 100 — beklenen ~80/10/10.
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
