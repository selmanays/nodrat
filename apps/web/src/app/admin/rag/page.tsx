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
  CitationStatsResponse,
  InspectQueryResponse,
  PipelineComparisonResponse,
  RagHealthResponse,
  RaptorClustersResponse,
  RaptorTriggerResponse,
  RerankStatsResponse,
  WeeklyClusterRow,
  ragBenchmarkHistory,
  ragBenchmarkRun,
  ragBenchmarkStatus,
  ragCitationStats,
  ragHealth,
  ragInspectQuery,
  ragPipelineComparison,
  ragRaptorClusters,
  ragRaptorTrigger,
  ragRerankStats,
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

// ============================================================================
// Sözlük — kısaltmalar / teknik terimler için tooltip metinleri
// ============================================================================

const HINTS = {
  ndcg10:
    "NDCG@10 (Normalize Edilmiş Kümülatif Kazanç). İlk 10 sonuçtaki sıralama kalitesini ölçer. 0–1 arası, 1 mükemmel sıralama. Doğru cevap ne kadar üstte ise puan o kadar yüksek.",
  map5:
    "MAP@5 (Ortalama Hassasiyet). İlk 5 sonuçta her doğru cevabın bulunduğu sıraya göre puan. 0–1 arası, yüksek iyi.",
  mrr10:
    "MRR@10 (Ortalama Karşılıklı Sıra). İlk doğru sonucun ortalama sırasının tersi. 1.0 = ilk sırada bulundu, 0.5 = 2. sırada, 0.33 = 3. sırada.",
  recall20:
    "Recall@20 (Geri Çağırma). İlk 20 sonuçta toplam doğru cevapların yakalanma oranı. 0–1 arası, yüksek iyi.",
  p5: "Precision@5 (Hassasiyet). İlk 5 sonucun ne kadarının doğru olduğu oranı.",
  p50: "p50 — Sorguların yarısı bu süreden hızlı tamamlandı (medyan).",
  p95: "p95 — Sorguların %95'i bu süreden hızlı tamamlandı.",
  raptor:
    "RAPTOR-Lite. Günlük gündem kartlarını embedding cosine benzerliğine göre kümeleyip DeepSeek özetiyle haftalık tema kartları üreten hiyerarşik kümeleme.",
  rrf:
    "RRF (Reciprocal Rank Fusion). Yoğun (embedding) ve sparse (trigram) arama sonuçlarını sıraya göre puanlayıp birleştirir. k=60 sabit.",
  reranker:
    "Yeniden Sıralayıcı. RRF'nin top-50 sonucunu cross-encoder ile yeniden puanlar; en alakalı 10'u öne çıkarır.",
  citation:
    "Atıf doğrulama. LLM çıktısının kaynak referanslarını embedding benzerliği ile kontrol eder; kanıtsız iddiaları işaretler.",
  candidatePool:
    "Aday havuzu. RRF füzyonuna alınan ilk N sonuç sayısı. Reranker bu havuzdan top-K'ya iner.",
  crossEncoder:
    "Cross-encoder. Sorgu + pasajı tek seferde değerlendiren model; bi-encoder'dan daha kaliteli ama yavaş.",
  importance:
    "Önem skoru. Kaynak çeşitliliği ve makale sayısına göre 0–1 arası puan; haber kümesinin gündem ağırlığını yansıtır.",
  insufficient:
    "Yeterli kaynak bulunamadı durumu. Sorgu için RAG ilgili agenda kartı bulamadığında dönen sonuç.",
  goldenSet:
    "Altın küme. Beklenen doğru cevapları (manuel hazırlanmış) içeren değerlendirme veri seti. retrieval_golden_tr.yaml içinde 50 Türkçe sorgu var.",
  daily:
    "Günlük gündem kartı. Tek bir olay kümesi için DeepSeek tarafından üretilen başlık + özet + kilit noktalar.",
  weekly:
    "Haftalık tema kartı. RAPTOR-Lite tarafından, son 7 günün benzer günlük kartlarından oluşturulan üst seviye özet.",
  unsupportedClaim:
    "Kanıtsız iddia. LLM'in ürettiği bir cümle için kaynak embedding benzerliği eşik altı kalan durumlar; halüsinasyon riski göstergesi.",
  generation: "Kullanıcı içerik üretim isteği (örn. tweet, özet).",
};

type TabKey =
  | "health"
  | "benchmark"
  | "citation"
  | "rerank"
  | "raptor"
  | "inspector"
  | "performance";

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: "health", label: "Sağlık" },
  { key: "benchmark", label: "Karşılaştırma" },
  { key: "citation", label: "Atıf" },
  { key: "rerank", label: "Yeniden Sıralama" },
  { key: "raptor", label: "RAPTOR" },
  { key: "inspector", label: "İnceleyici" },
  { key: "performance", label: "Performans" },
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
        <TabsContent value="raptor" className="mt-4">
          <RaptorTab />
        </TabsContent>
        <TabsContent value="inspector" className="mt-4">
          <InspectorTab />
        </TabsContent>
        <TabsContent value="performance" className="mt-4">
          <PerformanceTab />
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

  // #700 — Background polling: koşum sırasında 10s'de bir status çek
  useEffect(() => {
    if (!running) return;
    const interval = setInterval(async () => {
      try {
        const st = await ragBenchmarkStatus();
        if (!st.running) {
          // Tamamlandı — history refresh
          setRunning(false);
          setStatusMsg(
            st.error
              ? `Benchmark hata ile bitti: ${st.error}`
              : "Benchmark tamamlandı, history güncellendi."
          );
          load();
        } else {
          const elapsed = pollStartedAt
            ? Math.round((Date.now() - pollStartedAt) / 1000)
            : 0;
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

  const chartData = [...runs].reverse().map((r, i) => ({
    index: i + 1,
    started_at: r.started_at,
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
            Son {runs.length} çalıştırmanın{" "}
            <Term label="NDCG@10" hint={HINTS.ndcg10} /> /{" "}
            <Term label="MAP@5" hint={HINTS.map5} /> /{" "}
            <Term label="MRR@10" hint={HINTS.mrr10} /> değerleri
          </CardDescription>
          <CardAction>
            <div className="flex items-center gap-2">
              {/* #696 — suite seçici (chunks=production path; cards=legacy) */}
              <select
                value={suite}
                onChange={(e) =>
                  setSuite(e.target.value as "cards" | "chunks")
                }
                disabled={running}
                className="h-9 rounded-md border border-[var(--border)] bg-transparent px-2 text-sm"
                aria-label="Retrieval suite"
              >
                <option value="chunks">chunks (prod, NER+IDF)</option>
                <option value="cards">cards (legacy)</option>
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
// Atıf (Citation)
// ============================================================================

function CitationTab() {
  const [data, setData] = useState<CitationStatsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    ragCitationStats(100)
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
  if (!data) return <CitationSkeleton />;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Format düzeltmesi"
          value={data.repairs_total}
          subtitle={`son ${data.sample_size} üretim`}
        />
        <StatCard
          label="Düzeltme / üretim"
          value={data.repairs_avg_per_gen.toFixed(2)}
          subtitle="ortalama"
        />
        <StatCard
          label={
            <Term
              label="Kanıtsız iddia uyarısı"
              hint={HINTS.unsupportedClaim}
            />
          }
          value={data.unsupported_warnings}
          subtitle="hedef <%2"
        />
        <StatCard
          label="Kanıtsız iddia / üretim"
          value={data.unsupported_avg_per_gen.toFixed(2)}
        />
      </div>

      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader>
          <CardTitle className="text-base">
            Atıf Sağlığı{" "}
            <InfoTooltip
              content={HINTS.citation}
              className="ml-1 align-middle"
            />
          </CardTitle>
          <CardDescription>Doğrulama yöntemi ve eşikleri.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Atıf doğrulayıcı (#180) cümleleri kaynak embedding cosine ≥ 0.55 ile
            eşleştirir; format düzeltme regex tabanlıdır. (ID:N), (kaynak:N) →
            [#N] dönüşümü uygulanır.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function CitationSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card
            key={i}
            className="rounded-2xl shadow-none ring-[var(--border)]"
          >
            <CardHeader>
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-8 w-16" />
            </CardHeader>
          </Card>
        ))}
      </div>
    </div>
  );
}

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
  // #696 (B4) — suite seçici (chunks = NER + IDF + multi-entity AND telemetri)
  const [suite, setSuite] = useState<"cards" | "chunks">("chunks");
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
                  setSuite(e.target.value as "cards" | "chunks")
                }
                className="h-8 rounded-md border border-[var(--border)] bg-transparent px-2 text-xs"
              >
                <option value="chunks">chunks (prod, NER+IDF)</option>
                <option value="cards">cards (legacy)</option>
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

function StatCard({
  label,
  value,
  subtitle,
}: {
  label: React.ReactNode;
  value: number | string;
  subtitle?: string;
}) {
  return (
    <Card className="rounded-2xl shadow-none ring-[var(--border)]">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-3xl font-semibold tabular-nums">
          {value}
        </CardTitle>
        {subtitle && (
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        )}
      </CardHeader>
    </Card>
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

function KV({ k, v }: { k: React.ReactNode; v: string }) {
  return (
    <div className="flex items-center justify-between rounded-xl border p-3">
      <span className="text-sm text-muted-foreground">{k}</span>
      <span className="font-mono text-xs">{v}</span>
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

function fmt(n: number | null): string {
  if (n == null) return "—";
  return n.toFixed(4);
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
