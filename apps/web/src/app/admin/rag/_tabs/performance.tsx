"use client";

/**
 * Admin RAG sayfası — Performans (Pipeline Comparison) sekmesi (PR-7b-7).
 *
 * Phase 7b admin/rag mini-plan kapsamında 13 PR sırasının 8. adımı.
 * `METRIC_LABELS` + `METRIC_KEYS` + `DeltaBadge` + `PerformanceTab` (4 sembol)
 * page.tsx'ten saf taşıma (byte-for-byte korumalı); imza/davranış/JSX/render
 * değişikliği YOK.
 *
 * Tek API çağrısı: `ragPipelineComparison(params?)` — read-only GET
 * `/admin/rag/pipeline-comparison`. State-changing endpoint YOK.
 *
 * Interactive buttons (state-changing API trigger DEĞİL):
 * - "Karşılaştır" → `loadCustom()` → `ragPipelineComparison(params)` read-only
 * - "Default" → state reset + `loadDefault()` → `ragPipelineComparison({})` read-only
 *   (NER "Yenile" deseni — yalnız read-only GET re-fetch + UI state reset)
 *
 * Tab-local semboller (yalnız bu dosya kullanır):
 * - `METRIC_LABELS` (8 metric meta: label + format + betterDirection)
 * - `METRIC_KEYS` (8 metric key sırası)
 * - `DeltaBadge` (Δ% rozet — improvement/regression/neutral renkler)
 *
 * "use client" direktifi defensive olarak eklendi (PR-7b-1..6 deseni).
 *
 * Refs:
 * - wiki/topics/phase7b-admin-rag-mini-plan.md — Phase 7b mini-plan
 * - apps/web/src/app/admin/rag/page.tsx — root router (PerformanceTab import)
 */

import { useEffect, useState } from "react";

import {
  PipelineComparisonResponse,
  ragPipelineComparison,
} from "@/lib/api";
import { formatTrDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const METRIC_LABELS: Record<
  string,
  { label: string; format: (v: number | null) => string; betterDirection: "down" | "up" }
> = {
  avg_input_tokens: {
    label: "Ortalama input token",
    format: (v) => (v == null ? "—" : v.toFixed(0)),
    betterDirection: "down",
  },
  avg_output_tokens: {
    label: "Ortalama output token",
    format: (v) => (v == null ? "—" : v.toFixed(0)),
    betterDirection: "down",
  },
  cache_hit_ratio: {
    label: "Cache hit oranı",
    format: (v) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`),
    betterDirection: "up",
  },
  avg_cost_usd_per_req: {
    label: "Ortalama $/req",
    format: (v) => (v == null ? "—" : `$${v.toFixed(6)}`),
    betterDirection: "down",
  },
  p50_latency_ms: {
    label: "P50 latency",
    format: (v) => (v == null ? "—" : `${v} ms`),
    betterDirection: "down",
  },
  p95_latency_ms: {
    label: "P95 latency",
    format: (v) => (v == null ? "—" : `${v} ms`),
    betterDirection: "down",
  },
  halu_flag_rate: {
    label: "Halü oranı",
    format: (v) => (v == null ? "—" : `${(v * 100).toFixed(2)}%`),
    betterDirection: "down",
  },
  insufficient_data_rate: {
    label: "Yetersiz veri oranı",
    format: (v) => (v == null ? "—" : `${(v * 100).toFixed(2)}%`),
    betterDirection: "down",
  },
};

const METRIC_KEYS = [
  "avg_input_tokens",
  "avg_output_tokens",
  "cache_hit_ratio",
  "avg_cost_usd_per_req",
  "p50_latency_ms",
  "p95_latency_ms",
  "halu_flag_rate",
  "insufficient_data_rate",
];

function DeltaBadge({
  delta,
  betterDirection,
}: {
  delta: number | null;
  betterDirection: "down" | "up";
}) {
  if (delta == null) return <span className="text-muted-foreground text-xs">—</span>;

  const isImprovement =
    (betterDirection === "down" && delta < 0) ||
    (betterDirection === "up" && delta > 0);
  const isRegression =
    (betterDirection === "down" && delta > 0) ||
    (betterDirection === "up" && delta < 0);

  const sign = delta > 0 ? "+" : "";
  const text = `${sign}${delta.toFixed(2)}%`;

  if (Math.abs(delta) < 0.01) {
    return <Badge variant="outline">0%</Badge>;
  }
  if (isImprovement) {
    return (
      <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
        {text}
      </span>
    );
  }
  if (isRegression) {
    return (
      <span className="rounded-md bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-800 dark:bg-orange-900/40 dark:text-orange-300">
        {text}
      </span>
    );
  }
  return <Badge variant="outline">{text}</Badge>;
}

export function PerformanceTab() {
  const [data, setData] = useState<PipelineComparisonResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Tarih input'ları (boş bırakılırsa backend default'unu kullanır:
  // son 7d vs önceki 7d)
  const [fromA, setFromA] = useState("");
  const [toA, setToA] = useState("");
  const [fromB, setFromB] = useState("");
  const [toB, setToB] = useState("");

  // İlk açılışta default karşılaştırmayı çek
  useEffect(() => {
    void loadDefault();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadDefault() {
    setLoading(true);
    setError(null);
    try {
      const r = await ragPipelineComparison({});
      setData(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadCustom() {
    setLoading(true);
    setError(null);
    try {
      const params: {
        fromA?: string;
        toA?: string;
        fromB?: string;
        toB?: string;
      } = {};
      if (fromA) params.fromA = new Date(fromA).toISOString();
      if (toA) params.toA = new Date(toA).toISOString();
      if (fromB) params.fromB = new Date(fromB).toISOString();
      if (toB) params.toB = new Date(toB).toISOString();
      const r = await ragPipelineComparison(params);
      setData(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* #712 P1.1 — Mimari özet card (PR #693/#697/#701 sonrası mevcut katmanlar) */}
      <Card className="rounded-2xl shadow-none ring-[var(--border)] border-dashed">
        <CardHeader>
          <CardTitle className="text-base">RAG Pipeline Mimarisi (özet)</CardTitle>
          <CardDescription>
            Aşağıdaki LLM-cost karşılaştırması mevcut. Diğer pipeline metrikleri
            ilgili sekmelerde:
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-md border border-[var(--border)] p-3">
              <p className="text-xs text-muted-foreground">NER scoring</p>
              <p className="font-medium">Faz 6.1 — IDF + multi-entity AND</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Mode dağılımı: <strong>NER</strong> sekmesi
              </p>
            </div>
            <div className="rounded-md border border-[var(--border)] p-3">
              <p className="text-xs text-muted-foreground">HyDE</p>
              <p className="font-medium">Conditional (PR-C #686)</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Skip kararı: <strong>İnceleyici</strong> sekmesi
              </p>
            </div>
            <div className="rounded-md border border-[var(--border)] p-3">
              <p className="text-xs text-muted-foreground">Retrieval suite</p>
              <p className="font-medium">chunks (prod) + cards (legacy)</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Suite trend: <strong>Karşılaştırma</strong> sekmesi
              </p>
            </div>
            <div className="rounded-md border border-[var(--border)] p-3">
              <p className="text-xs text-muted-foreground">Cold-start warm-up</p>
              <p className="font-medium">PR-A #685 (embed + rerank)</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Süre metriği: <strong>Sağlık</strong> sekmesi
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Pipeline Performans Karşılaştırması</CardTitle>
          <CardDescription>
            İki tarih aralığında LLM çağrı metriklerini yan yana koyar (Content
            Generator + Query Planner). Default: son 7 gün (B) vs önceki 7 gün
            (A). Optimizasyon dalgaları sonrası retrospektif ölçüm için.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <p className="text-sm font-medium">Dönem A (önceki / baseline)</p>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-muted-foreground">Başlangıç</label>
                  <Input
                    type="datetime-local"
                    value={fromA}
                    onChange={(e) => setFromA(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Bitiş</label>
                  <Input
                    type="datetime-local"
                    value={toA}
                    onChange={(e) => setToA(e.target.value)}
                  />
                </div>
              </div>
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium">Dönem B (sonraki / karşılaştırma)</p>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-muted-foreground">Başlangıç</label>
                  <Input
                    type="datetime-local"
                    value={fromB}
                    onChange={(e) => setFromB(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Bitiş</label>
                  <Input
                    type="datetime-local"
                    value={toB}
                    onChange={(e) => setToB(e.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            <Button onClick={loadCustom} disabled={loading}>
              {loading ? "Yükleniyor..." : "Karşılaştır"}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setFromA("");
                setToA("");
                setFromB("");
                setToB("");
                void loadDefault();
              }}
              disabled={loading}
            >
              Default (son 7g vs önceki 7g)
            </Button>
          </div>
          {error && (
            <p className="text-sm text-destructive">Hata: {error}</p>
          )}
        </CardContent>
      </Card>

      {data && (
        <Card>
          <CardHeader>
            <CardTitle>Sonuç</CardTitle>
            <CardDescription>
              Dönem A: {formatTrDateTime(data.period_a.period_start)} —{" "}
              {formatTrDateTime(data.period_a.period_end)} ·{" "}
              {data.period_a.sample_count.toLocaleString("tr-TR")} LLM çağrısı,{" "}
              {data.period_a.completed_generation_count.toLocaleString("tr-TR")}{" "}
              üretim
              <br />
              Dönem B: {formatTrDateTime(data.period_b.period_start)} —{" "}
              {formatTrDateTime(data.period_b.period_end)} ·{" "}
              {data.period_b.sample_count.toLocaleString("tr-TR")} LLM çağrısı,{" "}
              {data.period_b.completed_generation_count.toLocaleString("tr-TR")}{" "}
              üretim
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Metrik</TableHead>
                  <TableHead className="text-right">Dönem A</TableHead>
                  <TableHead className="text-right">Dönem B</TableHead>
                  <TableHead className="text-right">Δ%</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {METRIC_KEYS.map((key) => {
                  const meta = METRIC_LABELS[key];
                  const a = (data.period_a as unknown as Record<string, number | null>)[key];
                  const b = (data.period_b as unknown as Record<string, number | null>)[key];
                  // insufficient_data_rate'in delta'sı backend'de hesaplanmıyor (acceptance dışı);
                  // diğerleri için delta_pct dictionary'sinden
                  const delta = data.delta_pct[key] ?? null;
                  return (
                    <TableRow key={key}>
                      <TableCell className="font-medium">{meta.label}</TableCell>
                      <TableCell className="text-right font-mono">
                        {meta.format(a)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {meta.format(b)}
                      </TableCell>
                      <TableCell className="text-right">
                        <DeltaBadge
                          delta={delta}
                          betterDirection={meta.betterDirection}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            <p className="mt-4 text-xs text-muted-foreground">
              Yeşil = iyileşme · Turuncu = regresyon · "—" = veri yetersiz (boş
              dönem veya A=0). Sadece <code>operation=&apos;chat&apos;</code> LLM
              çağrıları sayılır (embedding/rerank hariç). Halü ve yetersiz veri
              oranları yalnızca Content Generator çıktıları üzerinde.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
