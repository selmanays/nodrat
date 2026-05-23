"use client";

/**
 * Admin RAG Observability — Türkçe arayüz + tooltip'li kısaltmalar (#194)
 *
 * Epic #189 — sistem yöneticisi paneli RAG izleme.
 * Sekmeler: Sağlık / Karşılaştırma / Atıf / Yeniden Sıralama / RAPTOR / İnceleyici
 */

import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from "recharts";

import {
  BenchmarkRunSummary,
  InspectQueryResponse,
  PipelineComparisonResponse,
  RagHealthResponse,
  RaptorClustersResponse,
  RaptorTriggerResponse,
  RerankStatsResponse,
  CacheTelemetryResponse,
  WeeklyClusterRow,
  ragBenchmarkHistory,
  ragBenchmarkRun,
  ragBenchmarkStatus,
  ragHealth,
  ragInspectQuery,
  ragNerStats,
  ragPipelineComparison,
  ragRaptorClusters,
  ragRaptorTrigger,
  ragRerankStats,
  ragCacheTelemetry,
  type RagNerStatsResponse,
} from "@/lib/api";
import { formatTrDateTime } from "@/lib/format";
import { PageHeader } from "@/components/blocks/page-header";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip, Term } from "@/components/info-tooltip";

import { HINTS, StatCard, KV, fmt } from "./_shared";
import { CitationTab } from "./_tabs/citation";

// ============================================================================
// Sayfa tipi
// ============================================================================
//
// Ortak sembol göçü (PR-7b-1):
//   HINTS, StatCard, KV, fmt → `./_shared.tsx` (saf taşıma; byte-for-byte korumalı).
//   Tab fonksiyonları (HealthTab, BenchmarkTab, …) bu PR'da burada kalır;
//   sonraki PR-7b-2..7b-10'da `_tabs/*.tsx`'e taşınır.

type TabKey =
  | "health"
  | "benchmark"
  | "citation"
  | "rerank"
  | "ner"
  | "raptor"
  | "inspector"
  | "performance"
  | "cache";

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: "health", label: "Sağlık" },
  { key: "benchmark", label: "Karşılaştırma" },
  { key: "citation", label: "Atıf" },
  { key: "rerank", label: "Yeniden Sıralama" },
  { key: "ner", label: "NER" },  // #696 B5
  { key: "raptor", label: "RAPTOR" },
  { key: "inspector", label: "İnceleyici" },
  { key: "performance", label: "Performans" },
  { key: "cache", label: "Önbellek" },
];

export default function AdminRagPage() {
  const [tab, setTab] = useState<TabKey>("health");

  return (
    <div className="space-y-6">
      <PageHeader
        title="RAG İzlencesi"
        description="Değerlendirme, atıf, yeniden sıralama ve RAPTOR-Lite katmanlarının durumunu izleyin."
      />

      <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
        <TabsList aria-label="RAG sekmeleri">
          {TABS.map(({ key, label }) => (
            <TabsTrigger key={key} value={key}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="health" className="mt-4">
          <HealthTab />
        </TabsContent>
        <TabsContent value="benchmark" className="mt-4">
          <BenchmarkTab />
        </TabsContent>
        <TabsContent value="citation" className="mt-4">
          <CitationTab />
        </TabsContent>
        <TabsContent value="rerank" className="mt-4">
          <RerankTab />
        </TabsContent>
        <TabsContent value="ner" className="mt-4">
          <NerTab />
        </TabsContent>
        <TabsContent value="raptor" className="mt-4">
          <RaptorTab />
        </TabsContent>
        <TabsContent value="inspector" className="mt-4">
          <InspectorTab />
        </TabsContent>
        <TabsContent value="performance" className="mt-4">
          <PerformanceTab />
        </TabsContent>
        <TabsContent value="cache" className="mt-4">
          <CacheTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ============================================================================
// Sağlık (Health)
// ============================================================================

function HealthTab() {
  const [data, setData] = useState<RagHealthResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const load = () => {
      ragHealth()
        .then((r) => mounted && setData(r))
        .catch((e) => mounted && setErr(String(e)))
        .finally(() => mounted && setLoading(false));
    };
    load();
    const t = setInterval(load, 30000);
    return () => {
      mounted = false;
      clearInterval(t);
    };
  }, []);

  if (loading) return <HealthSkeleton />;
  if (err)
    return (
      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardContent className="p-4 text-sm text-destructive">
          Hata: {err}
        </CardContent>
      </Card>
    );
  if (!data) return null;

  return (
    <div className="space-y-6">
      {/* Sayılar — büyük metric grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          label={<Term label="Günlük kart" hint={HINTS.daily} />}
          value={data.counts.daily_cards}
        />
        <StatCard
          label={<Term label="Haftalık kart" hint={HINTS.weekly} />}
          value={data.counts.weekly_cards}
        />
        <StatCard
          label={<Term label="Üst kümeye bağlı kart" hint={HINTS.raptor} />}
          value={data.counts.daily_with_parent}
          subtitle="RAPTOR kümesi üyeleri"
        />
        <StatCard
          label="Aktif olay kümesi"
          value={data.counts.active_clusters}
        />
        <StatCard
          label={<Term label="Son 24s üretim" hint={HINTS.generation} />}
          value={data.counts.last_24h_generations}
        />
        <StatCard
          label={<Term label="Yetersiz veri" hint={HINTS.insufficient} />}
          value={data.counts.last_24h_insufficient}
          subtitle="son 24 saat"
        />
      </div>

      {/* Özellik anahtarları */}
      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader>
          <CardTitle className="text-base">Özellik Anahtarları</CardTitle>
          <CardDescription>
            RAG katmanının açık olan özellikleri ve aktif yapılandırma.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-2">
            <FlagRow
              label={<Term label="Yeniden Sıralayıcı" hint={HINTS.reranker} />}
              enabled={data.flags.reranker_enabled}
            />
            {/* #420 — "Yerel embedding" toggle kaldırıldı; embedding artık tek
                provider (local BAAI/bge-m3). */}
            <KV
              k={
                <Term
                  label="Yeniden sıralama modeli"
                  hint={HINTS.crossEncoder}
                />
              }
              v={data.flags.rerank_model}
            />
            <KV
              k={<Term label="Aday havuzu" hint={HINTS.candidatePool} />}
              v={String(data.flags.reranker_candidate_pool)}
            />
          </div>
        </CardContent>
      </Card>

      {/* #696 (B6) — Model warm-up metrik (PR-A #685 cold start fix) */}
      {data.warm_up && (
        <Card className="rounded-2xl shadow-none ring-[var(--border)]">
          <CardHeader>
            <CardTitle className="text-base">
              Model Warm-up{" "}
              <Badge
                variant={data.warm_up.ok ? "default" : "outline"}
                className="ml-2"
              >
                {data.warm_up.ok ? "OK" : "—"}
              </Badge>
            </CardTitle>
            <CardDescription>
              Startup'ta embedding + rerank model RAM'e yüklenir; cold-start
              ilk istek ~2-3s yerine ~50ms.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-3">
              <Metric
                label="Toplam süre"
                value={
                  data.warm_up.duration_ms != null
                    ? `${Math.round(data.warm_up.duration_ms)} ms`
                    : "—"
                }
              />
              <Metric
                label="Embedding"
                value={
                  data.warm_up.embedding_ms != null
                    ? `${Math.round(data.warm_up.embedding_ms)} ms`
                    : "—"
                }
              />
              <Metric
                label="Rerank"
                value={
                  data.warm_up.rerank_ms != null
                    ? `${Math.round(data.warm_up.rerank_ms)} ms`
                    : "—"
                }
              />
            </div>
            {data.warm_up.completed_at && (
              <p className="mt-3 text-xs text-muted-foreground">
                Son ısınma: {formatTrDateTime(data.warm_up.completed_at)}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Son eval */}
      {data.last_eval ? (
        <Card className="rounded-2xl shadow-none ring-[var(--border)]">
          <CardHeader>
            <CardTitle className="text-base">Son Karşılaştırma Sonucu</CardTitle>
            <CardDescription>
              <Term
                label={data.last_eval.golden_set}
                hint={HINTS.goldenSet}
              />{" "}
              ·{" "}
              {data.last_eval.completed_at
                ? formatTrDateTime(data.last_eval.completed_at)
                : "—"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-3">
              <Metric
                label={<Term label="NDCG@10" hint={HINTS.ndcg10} />}
                value={fmt(data.last_eval.ndcg_10)}
              />
              <Metric
                label={<Term label="MAP@5" hint={HINTS.map5} />}
                value={fmt(data.last_eval.map_5)}
              />
              <Metric
                label={<Term label="MRR@10" hint={HINTS.mrr10} />}
                value={fmt(data.last_eval.mrr_10)}
              />
              <Metric
                label={<Term label="Recall@20" hint={HINTS.recall20} />}
                value={fmt(data.last_eval.recall_20)}
              />
              <Metric
                label={<Term label="Gecikme p50" hint={HINTS.p50} />}
                value={`${data.last_eval.latency_ms_p50?.toFixed(0) ?? "—"} ms`}
              />
              <Metric
                label={<Term label="Gecikme p95" hint={HINTS.p95} />}
                value={`${data.last_eval.latency_ms_p95?.toFixed(0) ?? "—"} ms`}
              />
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="rounded-2xl shadow-none ring-[var(--border)]">
          <CardContent className="p-6 text-sm text-muted-foreground">
            Henüz değerlendirme kaydı yok.{" "}
            <strong className="text-foreground">Karşılaştırma</strong>{" "}
            sekmesinden başlatabilirsiniz.
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function HealthSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Card
            key={i}
            className="rounded-2xl shadow-none ring-[var(--border)]"
          >
            <CardHeader>
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-8 w-16" />
            </CardHeader>
          </Card>
        ))}
      </div>
      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader>
          <Skeleton className="h-5 w-40" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    </div>
  );
}

// ============================================================================
// Karşılaştırma (Benchmark)
// ============================================================================

const benchmarkChartConfig = {
  ndcg: { label: "NDCG@10", color: "var(--chart-1)" },
  map: { label: "MAP@5", color: "var(--chart-2)" },
  mrr: { label: "MRR@10", color: "var(--chart-3)" },
} satisfies ChartConfig;

function BenchmarkTab() {
  const [runs, setRuns] = useState<BenchmarkRunSummary[]>([]);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // #700 — Background polling state
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [pollStartedAt, setPollStartedAt] = useState<number | null>(null);

  const load = () => {
    ragBenchmarkHistory(20)
      .then((r) => setRuns(r.runs))
      .catch((e) => setErr(String(e)));
  };

  useEffect(() => {
    load();
  }, []);

  // #696 — suite seçici state (default chunks = production path)
  const [suite, setSuite] = useState<"cards" | "chunks">("chunks");

  // #700 + #712 B4 — Background polling: koşum sırasında 10s'de bir status çek.
  // false-erken-aktifleşme korumaları:
  //   1. Min 30s grace period (button basıldıktan sonra status running=false dönerse görmezden gel)
  //   2. completed_at timestamp + suite uyumu kontrolü
  useEffect(() => {
    if (!running) return;
    const interval = setInterval(async () => {
      try {
        const st = await ragBenchmarkStatus();
        const elapsed = pollStartedAt
          ? Math.round((Date.now() - pollStartedAt) / 1000)
          : 0;

        // #712 B4 — Min 30s grace: backend running flag false dönse bile,
        // tetiklemeden 30s geçmeden butonu açma (worker race / transient false)
        if (!st.running && elapsed < 30) {
          return;
        }

        if (!st.running) {
          setRunning(false);
          setStatusMsg(
            st.error
              ? `Benchmark hata ile bitti: ${st.error}`
              : `Benchmark tamamlandı (${elapsed}s, suite=${st.suite ?? "?"}), history güncellendi.`
          );
          load();
        } else {
          setStatusMsg(
            `Koşuyor (suite=${st.suite}, ~${elapsed}s geçti, toplam ~5-10dk)…`
          );
        }
      } catch {
        // Polling hatası kritik değil, ignore
      }
    }, 10_000);
    return () => clearInterval(interval);
  }, [running, pollStartedAt]);

  const trigger = async () => {
    setRunning(true);
    setErr(null);
    setStatusMsg("Başlatılıyor…");
    setPollStartedAt(Date.now());
    try {
      const resp = await ragBenchmarkRun(
        "retrieval_golden_tr.yaml",
        suite,
      );
      // #700 — Endpoint async döner; running state polling tarafından kapatılır
      setStatusMsg(
        resp.started
          ? `Benchmark arka planda başlatıldı (suite=${suite}). Tamamlanması ~5-10dk sürer; otomatik takip edilecek.`
          : (resp.message || "Başlatılamadı.")
      );
      if (!resp.started) {
        setRunning(false);
      }
    } catch (e) {
      setErr(String(e));
      setRunning(false);
    }
  };

  // #712 B4 — Chart suite-aware filtre: kullanıcının seçtiği suite ile aynı
  // koşumları göster. Eski koşumlarda suite null → "all" seçilirse gösterilir.
  const [chartSuiteFilter, setChartSuiteFilter] = useState<"all" | "cards" | "chunks">(
    "chunks",
  );
  const filteredRuns = runs.filter((r) => {
    if (chartSuiteFilter === "all") return true;
    return r.suite === chartSuiteFilter;
  });
  const chartData = [...filteredRuns].reverse().map((r, i) => ({
    index: i + 1,
    started_at: r.started_at,
    suite: r.suite ?? "?",
    ndcg: r.ndcg_10 ?? 0,
    map: r.map_5 ?? 0,
    mrr: r.mrr_10 ?? 0,
  }));

  return (
    <div className="space-y-6">
      {/* Trend chart */}
      <Card className="rounded-2xl pb-0 shadow-none ring-[var(--border)]">
        <CardHeader>
          <CardTitle className="text-base">
            Karşılaştırma Eğilimi
            <InfoTooltip
              content="Altın küme üzerinde retrieval pipeline'ın metric'lerinin zaman içindeki değişimi. Yeni özellik eklendiğinde çizgilerin yukarı kayması beklenir."
              className="ml-1 align-middle"
            />
          </CardTitle>
          <CardDescription>
            Son {filteredRuns.length} çalıştırmanın{" "}
            <Term label="NDCG@10" hint={HINTS.ndcg10} /> /{" "}
            <Term label="MAP@5" hint={HINTS.map5} /> /{" "}
            <Term label="MRR@10" hint={HINTS.mrr10} /> değerleri
            {chartSuiteFilter !== "all" && (
              <> · grafik filtresi: <Badge variant="secondary">{chartSuiteFilter}</Badge></>
            )}
          </CardDescription>
          <CardAction>
            <div className="flex items-center gap-2">
              {/* #712 B4 — chart suite filter (grafik için ayrı seçim) */}
              <select
                value={chartSuiteFilter}
                onChange={(e) =>
                  setChartSuiteFilter(e.target.value as "all" | "cards" | "chunks")
                }
                className="h-9 rounded-md border border-[var(--border)] bg-transparent px-2 text-sm"
                aria-label="Chart suite filter"
                title="Grafikte gösterilecek suite"
              >
                <option value="chunks">grafik: chunks</option>
                <option value="cards">grafik: cards</option>
                <option value="all">grafik: tümü</option>
              </select>
              {/* #696 — suite seçici (yeni koşum için) */}
              <select
                value={suite}
                onChange={(e) =>
                  setSuite(e.target.value as "cards" | "chunks")
                }
                disabled={running}
                className="h-9 rounded-md border border-[var(--border)] bg-transparent px-2 text-sm"
                aria-label="Retrieval suite (yeni koşum)"
                title="Yeni koşum için suite"
              >
                <option value="chunks">koşum: chunks (prod, NER+IDF)</option>
                <option value="cards">koşum: cards (legacy)</option>
              </select>
              <Button onClick={trigger} disabled={running}>
                {running
                  ? "Arka planda koşuyor… (~5-10dk)"
                  : "Karşılaştırmayı Çalıştır"}
              </Button>
            </div>
          </CardAction>
        </CardHeader>
        <CardContent className="px-0 pb-1">
          {err && (
            <p className="mb-3 px-6 text-sm text-destructive">{err}</p>
          )}
          {/* #700 — Background koşum durum mesajı */}
          {statusMsg && !err && (
            <p className="mb-3 px-6 text-sm text-muted-foreground">
              {statusMsg}
            </p>
          )}
          {chartData.length > 0 ? (
            <ChartContainer
              config={benchmarkChartConfig}
              className="h-64 w-full"
            >
              <LineChart
                data={chartData}
                margin={{ top: 4, right: 12, left: 12, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="index"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                />
                <YAxis
                  hide
                  domain={[0, 1]}
                />
                <ChartTooltip
                  cursor={false}
                  content={
                    <ChartTooltipContent
                      labelFormatter={(_label, payload) => {
                        const ts = payload?.[0]?.payload?.started_at as
                          | string
                          | undefined;
                        if (!ts) return "";
                        return formatTrDateTime(ts);
                      }}
                    />
                  }
                />
                <ChartLegend content={<ChartLegendContent />} />
                <Line
                  dataKey="ndcg"
                  type="monotone"
                  stroke="var(--color-ndcg)"
                  strokeWidth={1.5}
                  dot={false}
                />
                <Line
                  dataKey="map"
                  type="monotone"
                  stroke="var(--color-map)"
                  strokeWidth={1.5}
                  dot={false}
                />
                <Line
                  dataKey="mrr"
                  type="monotone"
                  stroke="var(--color-mrr)"
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ChartContainer>
          ) : (
            <p className="px-6 pb-6 text-sm text-muted-foreground">
              Henüz çalıştırma yok. Yukarıdaki "Karşılaştırmayı Çalıştır" ile
              başlatın.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Geçmiş tablosu — edge-to-edge */}
      <Card className="overflow-hidden rounded-2xl py-0 shadow-none ring-[var(--border)]">
        <Table>
          <TableHeader className="bg-muted/50">
            <TableRow>
              <TableHead>Tarih</TableHead>
              <TableHead>Suite</TableHead>
              <TableHead>Sorgu</TableHead>
              <TableHead>
                <Term label="NDCG@10" hint={HINTS.ndcg10} />
              </TableHead>
              <TableHead>
                <Term label="MAP@5" hint={HINTS.map5} />
              </TableHead>
              <TableHead>
                <Term label="MRR@10" hint={HINTS.mrr10} />
              </TableHead>
              <TableHead>
                <Term label="Recall@20" hint={HINTS.recall20} />
              </TableHead>
              <TableHead>
                <Term
                  label="Gecikme"
                  hint="Sorgu başına ortalama süre — p50 / p95 milisaniye"
                />{" "}
                p50/p95
              </TableHead>
              <TableHead>Tetikleyen</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="text-xs">
                  {formatTrDateTime(r.started_at)}
                </TableCell>
                <TableCell>
                  {r.suite ? (
                    <Badge
                      variant={r.suite === "chunks" ? "default" : "secondary"}
                    >
                      {r.suite}
                    </Badge>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell>{r.n_queries}</TableCell>
                <TableCell className="font-mono tabular-nums">
                  {fmt(r.ndcg_10)}
                </TableCell>
                <TableCell className="font-mono tabular-nums">
                  {fmt(r.map_5)}
                </TableCell>
                <TableCell className="font-mono tabular-nums">
                  {fmt(r.mrr_10)}
                </TableCell>
                <TableCell className="font-mono tabular-nums">
                  {fmt(r.recall_20)}
                </TableCell>
                <TableCell className="font-mono text-xs tabular-nums">
                  {r.latency_ms_p50?.toFixed(0) ?? "—"} /{" "}
                  {r.latency_ms_p95?.toFixed(0) ?? "—"}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {r.triggered_by ?? "—"}
                </TableCell>
              </TableRow>
            ))}
            {runs.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={8}
                  className="py-6 text-center text-muted-foreground"
                >
                  Henüz çalıştırma yok.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

// ============================================================================
// Atıf (Citation) — taşındı: ./_tabs/citation.tsx (PR-7b-2)
// ============================================================================

// ============================================================================
// Yeniden Sıralama (Reranker)
// ============================================================================

function RerankTab() {
  const [data, setData] = useState<RerankStatsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    ragRerankStats(24)
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err)
    return (
      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardContent className="p-4 text-sm text-destructive">
          Hata: {err}
        </CardContent>
      </Card>
    );
  if (!data) return <RerankSkeleton />;

  if (data.sample_size === 0) {
    return (
      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader>
          <CardTitle className="text-base">
            Yeniden Sıralayıcı{" "}
            <InfoTooltip
              content={HINTS.reranker}
              className="ml-1 align-middle"
            />
          </CardTitle>
          <CardDescription>son 24 saat</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Bu pencerede yeniden sıralama çağrısı yok. Trafik geldikçe metric'ler
            dolacak.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Çağrı sayısı"
          value={data.sample_size}
          subtitle="son 24 saat"
        />
        <StatCard
          label="Ortalama gecikme"
          value={`${data.avg_latency_ms?.toFixed(0) ?? "—"}`}
          subtitle="ms"
        />
        <StatCard
          label={<Term label="Gecikme p50" hint={HINTS.p50} />}
          value={`${data.p50_latency_ms?.toFixed(0) ?? "—"}`}
          subtitle="ms"
        />
        <StatCard
          label={<Term label="Gecikme p95" hint={HINTS.p95} />}
          value={`${data.p95_latency_ms?.toFixed(0) ?? "—"}`}
          subtitle="ms"
        />
      </div>

      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader>
          <CardTitle className="text-base">
            Yeniden Sıralayıcı{" "}
            <InfoTooltip
              content={HINTS.reranker}
              className="ml-1 align-middle"
            />
          </CardTitle>
          <CardDescription>Son çağrı zamanı.</CardDescription>
        </CardHeader>
        <CardContent>
          <KV
            k="Son çağrı"
            v={
              data.last_call_at ? formatTrDateTime(data.last_call_at) : "—"
            }
          />
        </CardContent>
      </Card>
    </div>
  );
}

function RerankSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card
            key={i}
            className="rounded-2xl shadow-none ring-[var(--border)]"
          >
            <CardHeader>
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-8 w-16" />
            </CardHeader>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// NER (#696 B5)
// ============================================================================

function NerTab() {
  const [data, setData] = useState<RagNerStatsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    ragNerStats()
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, [refreshKey]);

  if (err)
    return (
      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardContent className="p-4 text-sm text-destructive">
          Hata: {err}
        </CardContent>
      </Card>
    );
  if (!data) return <NerSkeleton />;

  const modes: Array<{
    key: string;
    label: string;
    description: string;
    color: "default" | "secondary" | "outline";
  }> = [
    {
      key: "multi_and",
      label: "Multi-AND",
      description: "2+ nadir entity intersect — en güçlü boost (K=20)",
      color: "default",
    },
    {
      key: "multi_and_common",
      label: "Multi-AND (common)",
      description: "Common entity AND dar intersect (<threshold) — K=20",
      color: "secondary",
    },
    {
      key: "single_rare",
      label: "Single rare",
      description: "1 nadir entity (Faz 6 eski seviye) — K=30",
      color: "secondary",
    },
    {
      key: "no_match",
      label: "No match",
      description: "Boost yok (sinyal güvensiz)",
      color: "outline",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Toplam NER sorgu"
          value={data.total}
          subtitle="process-lifetime sayım"
        />
        {modes.map((m) => {
          const count = data.distribution[m.key] || 0;
          const ratio = data.ratios[m.key] || 0;
          return (
            <StatCard
              key={m.key}
              label={m.label}
              value={count}
              subtitle={`%${(ratio * 100).toFixed(1)}`}
            />
          );
        })}
      </div>

      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader>
          <CardTitle className="text-base">
            NER Mode Dağılımı (Faz 6.1){" "}
            <InfoTooltip
              content="PR #693 IDF + multi-entity AND sonrası mode'lar. Multi-AND = en güçlü; no_match = boost devre dışı (sinyal güvensiz)."
              className="ml-1 align-middle"
            />
          </CardTitle>
          <CardDescription>
            Her sorgu için NER stream'in seçtiği mode dağılımı.
          </CardDescription>
          <CardAction>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setRefreshKey((k) => k + 1)}
            >
              Yenile
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Mode</TableHead>
                <TableHead className="text-right">Sayı</TableHead>
                <TableHead className="text-right">Oran</TableHead>
                <TableHead>Açıklama</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {modes.map((m) => {
                const count = data.distribution[m.key] || 0;
                const ratio = data.ratios[m.key] || 0;
                return (
                  <TableRow key={m.key}>
                    <TableCell>
                      <Badge variant={m.color}>{m.label}</Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {count}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      %{(ratio * 100).toFixed(1)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {m.description}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <p className="mt-4 text-xs text-muted-foreground">{data.note}</p>
          {data.first_seen && data.last_seen && (
            <p className="mt-2 text-xs text-muted-foreground">
              İlk sorgu: {formatTrDateTime(data.first_seen)} · Son sorgu:{" "}
              {formatTrDateTime(data.last_seen)}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function NerSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Card
            key={i}
            className="rounded-2xl shadow-none ring-[var(--border)]"
          >
            <CardHeader>
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-8 w-16" />
            </CardHeader>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// RAPTOR
// ============================================================================

function RaptorTab() {
  const [data, setData] = useState<RaptorClustersResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [trigResult, setTrigResult] = useState<RaptorTriggerResponse | null>(
    null,
  );
  const [err, setErr] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = () => {
    ragRaptorClusters(20)
      .then(setData)
      .catch((e) => setErr(String(e)));
  };

  useEffect(() => {
    load();
  }, []);

  const trigger = async () => {
    setRunning(true);
    setErr(null);
    try {
      const r = await ragRaptorTrigger();
      setTrigResult(r);
      load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader>
          <CardTitle className="text-base">
            RAPTOR-Lite Haftalık Kümeler{" "}
            <InfoTooltip
              content={HINTS.raptor}
              className="ml-1 align-middle"
            />
          </CardTitle>
          <CardDescription>
            Günlük gündem kartları haftalık tema kart altında gruplanır.
          </CardDescription>
          <CardAction>
            <Button onClick={trigger} disabled={running}>
              {running ? "Çalışıyor…" : "Şimdi Oluştur"}
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          {err && <p className="mb-3 text-sm text-destructive">{err}</p>}
          {trigResult && (
            <p className="rounded-xl bg-muted/50 px-3 py-2 text-sm">
              {trigResult.daily_count} günlük → {trigResult.cluster_count} küme
              (başarılı: {trigResult.ok_count})
            </p>
          )}
        </CardContent>
      </Card>

      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardContent className="p-4">
          <div className="space-y-3">
            {data?.weekly.map((w) => (
              <ClusterRow
                key={w.id}
                cluster={w}
                expanded={expanded === w.id}
                onToggle={() => setExpanded(expanded === w.id ? null : w.id)}
              />
            ))}
            {!data?.weekly.length && (
              <p className="py-6 text-center text-sm text-muted-foreground">
                Henüz haftalık küme yok. Yukarıdaki "Şimdi Oluştur" ile
                tetikleyin.
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ClusterRow({
  cluster,
  expanded,
  onToggle,
}: {
  cluster: WeeklyClusterRow;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="rounded-xl border p-3">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between text-left"
      >
        <div className="flex-1 pr-4">
          <p className="font-medium">{cluster.title}</p>
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
            {cluster.summary}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="secondary">
            {cluster.daily_children_count} günlük
          </Badge>
          {cluster.importance != null && (
            <Badge variant="outline">
              <Term
                label={`önem ${cluster.importance.toFixed(2)}`}
                hint={HINTS.importance}
              />
            </Badge>
          )}
        </div>
      </button>
      {expanded && cluster.children_titles.length > 0 && (
        <ul className="mt-3 space-y-1 border-t pt-3 text-sm">
          {cluster.children_titles.map((t, i) => (
            <li key={i} className="text-muted-foreground">
              • {t}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ============================================================================
// İnceleyici (Inspector)
// ============================================================================

function InspectorTab() {
  const [query, setQuery] = useState("");
  const [usePlanner, setUsePlanner] = useState(true);
  // #718 — Default "production" suite (cards primary + chunks fallback,
  // gerçek /api/generate akışını birebir simüle eder)
  const [suite, setSuite] = useState<"cards" | "chunks" | "production">(
    "production",
  );
  const [data, setData] = useState<InspectQueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setErr(null);
    try {
      const r = await ragInspectQuery(query, 10, 80, usePlanner, suite);
      setData(r);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader>
          <CardTitle className="text-base">
            Sorgu İnceleyici{" "}
            <InfoTooltip
              content="Bir sorguyu retrieval pipeline'a gönderir; RRF skorları ile yeniden sıralayıcı skorlarını yan yana gösterir. Kalite hatalarını teşhis için."
              className="ml-1 align-middle"
            />
          </CardTitle>
          <CardDescription>
            Pipeline çıktısını uçtan uca incele.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Input
              placeholder='örn. "izmir çevre yolu ücretli mi olacak"'
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
            />
            <Button
              onClick={submit}
              disabled={loading || query.trim().length < 2}
            >
              {loading ? "Çalışıyor…" : "İncele"}
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Switch
              id="rag-use-planner"
              checked={usePlanner}
              onCheckedChange={setUsePlanner}
            />
            <label
              htmlFor="rag-use-planner"
              className="text-sm text-muted-foreground"
            >
              Query Planner ile zenginleştir{" "}
              <InfoTooltip content="LLM ile sorgudan ana konu + 3-5 keyword çıkar; bunları arama metnine ekle. Kullanıcı tarafındaki gerçek davranışı simüle eder." />
            </label>
            <div className="flex items-center gap-2 ml-auto">
              <span className="text-sm text-muted-foreground">Suite:</span>
              <select
                value={suite}
                onChange={(e) =>
                  setSuite(e.target.value as "cards" | "chunks" | "production")
                }
                className="h-8 rounded-md border border-[var(--border)] bg-transparent px-2 text-xs"
                title="production: gerçek /api/generate akışı (cards primary + chunks fallback)"
              >
                <option value="production">production (gerçek /generate akışı)</option>
                <option value="cards">cards (sadece agenda)</option>
                <option value="chunks">chunks (sadece article)</option>
              </select>
            </div>
          </div>
          {err && <p className="text-sm text-destructive">{err}</p>}
        </CardContent>
      </Card>

      {data?.planner?.used && (
        <Card className="rounded-2xl shadow-none ring-[var(--border)]">
          <CardHeader>
            <CardTitle className="text-base">Planner Çıktısı</CardTitle>
            <CardDescription>
              Sorgu planlayıcısının zenginleştirme adımları.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div>
                <span className="text-muted-foreground">Konu:</span>{" "}
                <span className="font-mono text-xs">
                  {data.planner.topic_query}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-muted-foreground">Anahtar kelimeler:</span>{" "}
                {data.planner.keywords.map((k) => (
                  <Badge key={k} variant="secondary">
                    {k}
                  </Badge>
                ))}
              </div>
              <div>
                <span className="text-muted-foreground">Zengin sorgu:</span>{" "}
                <code className="rounded bg-muted px-2 py-0.5 text-xs">
                  {data.planner.enriched_query}
                </code>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* #725 — Timeframe SQL filter telemetri (production parity) */}
      {data?.timeframe?.enabled && (
        <Card className="rounded-2xl shadow-none ring-[var(--border)]">
          <CardHeader>
            <CardTitle className="text-base">Zaman Aralığı (SQL filter)</CardTitle>
            <CardDescription>
              Planner&apos;ın çıkardığı timeframe&apos;ler — production&apos;da
              <code className="mx-1 rounded bg-muted px-1.5 py-0.5 text-xs">
                hybrid_search_*(timeframe_from, timeframe_to)
              </code>
              olarak SQL&apos;e geçer.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-muted-foreground">Pencereler:</span>{" "}
                {data.timeframe.timeframes.length === 0 ? (
                  <span className="text-xs text-muted-foreground">(yok)</span>
                ) : (
                  data.timeframe.timeframes.map((tf, i) => (
                    <Badge key={i} variant="outline" className="font-mono">
                      {tf.label}: {tf.from.slice(0, 10)} → {tf.to.slice(0, 10)}
                    </Badge>
                  ))
                )}
              </div>
              {data.timeframe.effective_from && data.timeframe.effective_to && (
                <div className="text-xs">
                  <span className="text-muted-foreground">
                    Etkin SQL filter:
                  </span>{" "}
                  <code className="rounded bg-muted px-1.5 py-0.5">
                    {data.timeframe.effective_from.slice(0, 19)} →{" "}
                    {data.timeframe.effective_to.slice(0, 19)}
                  </code>
                  {data.timeframe.span_days != null && (
                    <span className="ml-2 text-muted-foreground">
                      (span {data.timeframe.span_days.toFixed(1)} gün)
                    </span>
                  )}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* #725 — Sufficiency gate telemetri (production'da burada erken çıkar) */}
      {data?.sufficiency?.enabled && (
        <Card
          className={`rounded-2xl shadow-none ring-[var(--border)] ${
            data.sufficiency.would_have_exited
              ? "border-amber-500/40 bg-amber-500/5"
              : ""
          }`}
        >
          <CardHeader>
            <CardTitle className="text-base">
              Sufficiency Gate{" "}
              <Badge
                variant={
                  data.sufficiency.would_have_exited
                    ? "destructive"
                    : data.sufficiency.sufficient
                    ? "default"
                    : "secondary"
                }
                className="ml-2"
              >
                {data.sufficiency.would_have_exited
                  ? "⚠ prod'da erken çıkardı"
                  : data.sufficiency.sufficient
                  ? "yeterli"
                  : "yetersiz (gate enforce edilmedi)"}
              </Badge>
            </CardTitle>
            <CardDescription>
              Production&apos;da{" "}
              <code className="mx-1 rounded bg-muted px-1.5 py-0.5 text-xs">
                mode=&apos;current&apos;
              </code>
              + yetersiz ise <code className="rounded bg-muted px-1.5 py-0.5">insufficient_data</code>{" "}
              ile erken çıkar. Inspector tanı amaçlı çalıştırır — retrieval&apos;a devam eder.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="flex flex-wrap items-center gap-3">
                <span>
                  <span className="text-muted-foreground">Mode:</span>{" "}
                  <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                    {data.sufficiency.mode}
                  </code>
                </span>
                <span>
                  <span className="text-muted-foreground">Min evidence:</span>{" "}
                  <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                    {data.sufficiency.min_evidence_per_period}
                  </code>
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-muted-foreground">Dönem sayıları:</span>{" "}
                {Object.entries(data.sufficiency.counts_per_period).length === 0 ? (
                  <span className="text-xs text-muted-foreground">(yok)</span>
                ) : (
                  Object.entries(data.sufficiency.counts_per_period).map(
                    ([label, count]) => (
                      <Badge
                        key={label}
                        variant={
                          count < data.sufficiency!.min_evidence_per_period
                            ? "destructive"
                            : "secondary"
                        }
                        className="font-mono"
                      >
                        {label}: {count}
                      </Badge>
                    ),
                  )
                )}
              </div>
              {data.sufficiency.reason && (
                <div className="text-xs text-muted-foreground">
                  {data.sufficiency.reason}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* #696 (B4) — NER pipeline telemetri (chunks suite'inde aktif) */}
      {data?.ner?.enabled && (
        <Card className="rounded-2xl shadow-none ring-[var(--border)]">
          <CardHeader>
            <CardTitle className="text-base">
              NER Çözümlemesi (Faz 6.1){" "}
              <Badge
                variant={
                  data.ner.mode === "multi_and"
                    ? "default"
                    : data.ner.mode === "single_rare"
                    ? "secondary"
                    : data.ner.mode === "multi_and_common"
                    ? "secondary"
                    : "outline"
                }
                className="ml-2"
              >
                {data.ner.mode}
              </Badge>
            </CardTitle>
            <CardDescription>
              IDF + multi-entity AND scoring; mode &amp; df_map &amp; aday article'lar.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-muted-foreground">Entity adayları:</span>{" "}
                {data.ner.query_entities.length === 0 ? (
                  <span className="text-xs text-muted-foreground">
                    (yok)
                  </span>
                ) : (
                  data.ner.query_entities.map((e) => (
                    <Badge key={e} variant="outline" className="font-mono">
                      {e} (df={data.ner!.df_map[e] ?? "?"})
                    </Badge>
                  ))
                )}
              </div>
              <div>
                <span className="text-muted-foreground">
                  Hedef article sayısı:
                </span>{" "}
                <span className="font-mono">
                  {data.ner.target_aids_count}
                </span>
              </div>
              {data.ner.target_aids_sample.length > 0 && (
                <div className="text-xs text-muted-foreground">
                  Örnek aid (ilk 10):{" "}
                  <code className="rounded bg-muted px-1.5 py-0.5">
                    {data.ner.target_aids_sample
                      .map((a) => a.slice(0, 8))
                      .join(", ")}
                  </code>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* #742 (Faz 7c Aşama 1) — Answer extraction diagnostic */}
      {data && (data.reranked_top.some((r) => (r.answer_span_candidates?.length ?? 0) > 0) ||
        (data.parent_doc_merge?.length ?? 0) > 0) && (
        <Card className="rounded-2xl shadow-none ring-[var(--border)]">
          <CardHeader>
            <CardTitle className="text-base">
              Answer Extraction Diagnostic (Faz 7c Aşama 1)
            </CardTitle>
            <CardDescription>
              Chunk içi numerical span'lar + parent doc cross-chunk grupları.
              Diagnostic — Aşama 2-4 implementation öncesi fail vakaları analizi.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4 text-sm">
              {/* Top-5 row answer span listesi */}
              {data.reranked_top.slice(0, 5).some((r) => (r.answer_span_candidates?.length ?? 0) > 0) && (
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">
                    Top-5 chunk numerical span'ları:
                  </p>
                  <div className="space-y-1">
                    {data.reranked_top.slice(0, 5).map((r, i) => {
                      const spans = r.answer_span_candidates ?? [];
                      if (spans.length === 0) return null;
                      return (
                        <div
                          key={r.id}
                          className="flex flex-wrap items-center gap-1.5 text-xs"
                        >
                          <span className="font-mono text-muted-foreground">
                            #{i + 1}
                          </span>
                          <span className="line-clamp-1 max-w-xs text-muted-foreground">
                            {r.title.slice(0, 50)}
                          </span>
                          {spans.map((s, j) => (
                            <Badge key={j} variant="secondary" className="font-mono">
                              {s}
                            </Badge>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Parent doc merge groups */}
              {(data.parent_doc_merge?.length ?? 0) > 0 && (
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">
                    Parent doc merge adayları (aynı article'dan 2+ chunk):
                  </p>
                  <div className="space-y-2">
                    {(data.parent_doc_merge ?? []).slice(0, 5).map((g) => (
                      <div
                        key={g.article_id}
                        className="rounded-lg border bg-muted/30 p-2 text-xs"
                      >
                        <div className="mb-1 flex items-center gap-2">
                          <Badge variant="outline" className="font-mono">
                            {g.chunk_count} chunk
                          </Badge>
                          <span className="line-clamp-1 font-medium">
                            {g.article_title || g.article_id.slice(0, 8)}
                          </span>
                        </div>
                        <div className="space-y-0.5 text-muted-foreground">
                          {g.chunks.slice(0, 3).map((c) => (
                            <div key={c.chunk_id}>
                              <span className="font-mono">#{c.rank}</span>{" "}
                              {c.excerpt.slice(0, 120)}…
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {data && (
        <Card className="overflow-hidden rounded-2xl py-0 shadow-none ring-[var(--border)]">
          <div className="flex items-center justify-between gap-2 border-b bg-muted/50 px-4 py-3">
            <div>
              <p className="text-sm font-medium">Yeniden Sıralanmış İlk 10</p>
              <p className="text-xs text-muted-foreground">
                Δ &gt; 0: yeniden sıralayıcı bu sonucu yukarı taşıdı. Δ &lt; 0:
                aşağı düşürdü.
              </p>
            </div>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead>
                <TableHead>Başlık</TableHead>
                <TableHead>
                  <Term label="RRF" hint={HINTS.rrf} />
                </TableHead>
                <TableHead>
                  <Term
                    label="Alaka"
                    hint="Cross-encoder ham logit'i sigmoid ile 0-1 aralığına normalize edildi. ≥0.5 güçlü alaka, 0.1-0.5 zayıf, <0.1 alakasız."
                  />
                </TableHead>
                <TableHead>
                  <Term
                    label="RRF sırası"
                    hint="Yeniden sıralama yapılmasaydı bu sonuç hangi sırada olurdu."
                  />
                </TableHead>
                <TableHead>
                  <Term
                    label="Δ"
                    hint="Sıralama değişimi. ↑ = cross-encoder yukarı taşıdı, ↓ = aşağı düşürdü."
                  />
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.reranked_top.map((r, i) => {
                const delta =
                  r.rrf_rank != null ? r.rrf_rank - (i + 1) : null;
                return (
                  <TableRow key={r.id}>
                    <TableCell className="font-mono tabular-nums">
                      {i + 1}
                    </TableCell>
                    <TableCell>{r.title}</TableCell>
                    <TableCell className="font-mono text-xs tabular-nums">
                      {r.rrf_score?.toFixed(3) ?? "—"}
                    </TableCell>
                    <TableCell>
                      <RerankBadge logit={r.rerank_score} />
                    </TableCell>
                    <TableCell className="font-mono text-xs tabular-nums">
                      {r.rrf_rank ?? "—"}
                    </TableCell>
                    <TableCell className="font-mono text-xs tabular-nums">
                      {delta == null ? (
                        "—"
                      ) : (
                        <span
                          className={
                            delta > 0
                              ? "text-emerald-600 dark:text-emerald-400"
                              : delta < 0
                                ? "text-orange-600 dark:text-orange-400"
                                : "text-muted-foreground"
                          }
                        >
                          {delta > 0
                            ? `↑${delta}`
                            : delta < 0
                              ? `↓${-delta}`
                              : "0"}
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}

// ============================================================================
// Yardımcı bileşenler
// ============================================================================

function CacheTab() {
  const [data, setData] = useState<CacheTelemetryResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    ragCacheTelemetry(24)
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  const pct = (v: number | null) =>
    v === null || v === undefined ? "—" : `%${(v * 100).toFixed(1)}`;

  if (err)
    return (
      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardContent className="p-4 text-sm text-destructive">
          Hata: {err}
        </CardContent>
      </Card>
    );
  if (!data)
    return (
      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardContent className="p-4 text-sm text-muted-foreground">
          Yükleniyor…
        </CardContent>
      </Card>
    );

  if (data.total_calls === 0)
    return (
      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader>
          <CardTitle className="text-base">Önbellek Telemetrisi</CardTitle>
          <CardDescription>son {data.window_hours} saat</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Bu pencerede research LLM çağrısı yok. Araştırma trafiği geldikçe
            metrikler dolacak (token-bazlı, fiyattan bağımsız).
          </p>
        </CardContent>
      </Card>
    );

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Cache-hit oranı"
          value={pct(data.overall_cache_hit_ratio)}
          subtitle={`son ${data.window_hours} saat · token-bazlı`}
        />
        <StatCard
          label="LLM çağrısı"
          value={data.total_calls}
          subtitle="research hattı"
        />
        <StatCard
          label="Miss token"
          value={data.total_miss_tokens.toLocaleString()}
          subtitle={`/ ${data.total_input_tokens.toLocaleString()} input`}
        />
        <StatCard
          label="Cached token"
          value={data.total_cached_tokens.toLocaleString()}
          subtitle="prefix yeniden kullanım"
        />
      </div>

      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader>
          <CardTitle className="text-base">
            Çağrı tipine göre (Senaryo-B göstergesi)
          </CardTitle>
          <CardDescription>
            forced_final düşük cache-hit + düşük tools_present = #983 sinyali
          </CardDescription>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-1 pr-4">call_type</th>
                <th className="py-1 pr-4">çağrı</th>
                <th className="py-1 pr-4">cache-hit</th>
                <th className="py-1 pr-4">tools_present</th>
                <th className="py-1 pr-4">miss token</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {data.by_call_type.map((r) => (
                <tr
                  key={r.call_type}
                  className="border-t border-[var(--border)]"
                >
                  <td className="py-1 pr-4 font-medium">{r.call_type}</td>
                  <td className="py-1 pr-4">{r.calls}</td>
                  <td className="py-1 pr-4">{pct(r.cache_hit_ratio)}</td>
                  <td className="py-1 pr-4">{pct(r.tools_present_rate)}</td>
                  <td className="py-1 pr-4">
                    {r.miss_tokens.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function FlagRow({
  label,
  enabled,
}: {
  label: React.ReactNode;
  enabled: boolean;
}) {
  return (
    <div className="flex items-center justify-between rounded-xl border p-3">
      <span className="text-sm">{label}</span>
      <div className="flex items-center gap-2">
        <span
          className={
            enabled
              ? "text-xs font-medium text-emerald-600 dark:text-emerald-400"
              : "text-xs font-medium text-muted-foreground"
          }
        >
          {enabled ? "AÇIK" : "KAPALI"}
        </span>
        <Switch checked={enabled} disabled />
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  subtitle,
}: {
  label: React.ReactNode;
  value: number | string;
  subtitle?: string;
}) {
  return (
    <div className="rounded-xl border p-3">
      <p className="text-xs uppercase text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-2xl">{value}</p>
      {subtitle && (
        <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
      )}
    </div>
  );
}

/**
 * Cross-encoder ham logit (-∞..+∞) → sigmoid (0..1) + renkli rozet.
 * ≥0.5 yeşil (güçlü alaka), ≥0.1 sarı (zayıf), <0.1 gri (alakasız).
 */
function RerankBadge({ logit }: { logit: number | null }) {
  if (logit == null) return <span className="text-muted-foreground">—</span>;
  const score = 1 / (1 + Math.exp(-logit));
  const text = score.toFixed(3);
  if (score >= 0.5) return <Badge variant="secondary">{text}</Badge>;
  if (score >= 0.1) return <Badge variant="outline">{text}</Badge>;
  return <Badge variant="secondary">{text} · düşük</Badge>;
}

// ============================================================================
// Performans (Pipeline Comparison) — #440
// ============================================================================

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

function PerformanceTab() {
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
