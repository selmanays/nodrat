"use client";

/**
 * Admin RAG Observability — Türkçe arayüz + tooltip'li kısaltmalar (#194)
 *
 * Epic #189 — sistem yöneticisi paneli RAG izleme.
 * Sekmeler: Sağlık / Karşılaştırma / Atıf / Yeniden Sıralama / RAPTOR / İnceleyici
 */

import { useEffect, useState } from "react";
import {
  Activity,
  BarChart3,
  Database,
  FileSearch,
  Quote,
  Sparkles,
  Zap,
} from "lucide-react";

import {
  BenchmarkRunSummary,
  CitationStatsResponse,
  InspectQueryResponse,
  RagHealthResponse,
  RaptorClustersResponse,
  RaptorTriggerResponse,
  RerankStatsResponse,
  WeeklyClusterRow,
  ragBenchmarkHistory,
  ragBenchmarkRun,
  ragCitationStats,
  ragHealth,
  ragInspectQuery,
  ragRaptorClusters,
  ragRaptorTrigger,
  ragRerankStats,
} from "@/lib/api";
import { formatTrDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { InfoTooltip, Term } from "@/components/ui/tooltip";

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
  | "inspector";

const TABS: Array<{ key: TabKey; label: string; icon: React.ElementType }> = [
  { key: "health", label: "Sağlık", icon: Activity },
  { key: "benchmark", label: "Karşılaştırma", icon: BarChart3 },
  { key: "citation", label: "Atıf", icon: Quote },
  { key: "rerank", label: "Yeniden Sıralama", icon: Zap },
  { key: "raptor", label: "RAPTOR", icon: Database },
  { key: "inspector", label: "İnceleyici", icon: FileSearch },
];

export default function AdminRagPage() {
  const [tab, setTab] = useState<TabKey>("health");

  return (
    <div className="space-y-6">
      <header className="flex items-center gap-3">
        <Sparkles className="h-7 w-7 text-primary" />
        <div>
          <h1 className="text-2xl font-semibold">RAG Gözlem Paneli</h1>
          <p className="text-sm text-muted-foreground">
            Değerlendirme, atıf, yeniden sıralama ve RAPTOR-Lite katmanlarının
            durumunu izleyin.
          </p>
        </div>
      </header>

      <nav
        className="flex flex-wrap gap-2 border-b border-border pb-2"
        aria-label="RAG sekmeleri"
      >
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors ${
              tab === key
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted"
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </nav>

      {tab === "health" && <HealthTab />}
      {tab === "benchmark" && <BenchmarkTab />}
      {tab === "citation" && <CitationTab />}
      {tab === "rerank" && <RerankTab />}
      {tab === "raptor" && <RaptorTab />}
      {tab === "inspector" && <InspectorTab />}
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

  if (loading)
    return <p className="text-sm text-muted-foreground">Yükleniyor…</p>;
  if (err) return <p className="text-sm text-destructive">Hata: {err}</p>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <h3 className="mb-3 text-base font-semibold">Özellik Anahtarları</h3>
        <div className="grid gap-3 md:grid-cols-2">
          <FlagRow
            label={
              <Term label="Yeniden Sıralayıcı" hint={HINTS.reranker} />
            }
            enabled={data.flags.reranker_enabled}
          />
          <FlagRow
            label="Yerel embedding"
            enabled={data.flags.use_local_embedding}
          />
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
            k={
              <Term
                label="Aday havuzu"
                hint={HINTS.candidatePool}
              />
            }
            v={String(data.flags.reranker_candidate_pool)}
          />
        </div>
      </Card>

      <Card className="p-4">
        <h3 className="mb-3 text-base font-semibold">Sayılar</h3>
        <div className="grid gap-3 md:grid-cols-3">
          <Metric
            label={<Term label="Günlük kart" hint={HINTS.daily} />}
            value={data.counts.daily_cards}
          />
          <Metric
            label={<Term label="Haftalık kart" hint={HINTS.weekly} />}
            value={data.counts.weekly_cards}
          />
          <Metric
            label={
              <Term label="Üst kümeye bağlı kart" hint={HINTS.raptor} />
            }
            value={data.counts.daily_with_parent}
            subtitle="RAPTOR kümesi üyeleri"
          />
          <Metric
            label="Aktif olay kümesi"
            value={data.counts.active_clusters}
          />
          <Metric
            label={<Term label="Son 24s üretim" hint={HINTS.generation} />}
            value={data.counts.last_24h_generations}
          />
          <Metric
            label={
              <Term label="Yetersiz veri" hint={HINTS.insufficient} />
            }
            value={data.counts.last_24h_insufficient}
            subtitle="son 24 saat"
          />
        </div>
      </Card>

      {data.last_eval ? (
        <Card className="p-4">
          <h3 className="mb-3 text-base font-semibold">
            Son Karşılaştırma Sonucu
          </h3>
          <p className="mb-2 text-xs text-muted-foreground">
            <Term label={data.last_eval.golden_set} hint={HINTS.goldenSet} /> ·{" "}
            {data.last_eval.completed_at
              ? formatTrDateTime(data.last_eval.completed_at)
              : "—"}
          </p>
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
        </Card>
      ) : (
        <Card className="p-4">
          <p className="text-sm text-muted-foreground">
            Henüz değerlendirme kaydı yok. <strong>Karşılaştırma</strong>{" "}
            sekmesinden başlatabilirsiniz.
          </p>
        </Card>
      )}
    </div>
  );
}

// ============================================================================
// Karşılaştırma (Benchmark)
// ============================================================================

function BenchmarkTab() {
  const [runs, setRuns] = useState<BenchmarkRunSummary[]>([]);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    ragBenchmarkHistory(20)
      .then((r) => setRuns(r.runs))
      .catch((e) => setErr(String(e)));
  };

  useEffect(() => {
    load();
  }, []);

  const trigger = async () => {
    setRunning(true);
    setErr(null);
    try {
      await ragBenchmarkRun();
      load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold">
              Karşılaştırma Eğilimi
              <InfoTooltip
                content="Altın küme üzerinde retrieval pipeline'ın metric'lerinin zaman içindeki değişimi. Yeni özellik eklendiğinde çizgilerin yukarı kayması beklenir."
                className="ml-1 align-middle"
              />
            </h3>
            <p className="text-xs text-muted-foreground">
              Son {runs.length} çalıştırmanın <Term label="NDCG@10" hint={HINTS.ndcg10} /> /{" "}
              <Term label="MAP@5" hint={HINTS.map5} /> /{" "}
              <Term label="MRR@10" hint={HINTS.mrr10} /> değerleri
            </p>
          </div>
          <Button onClick={trigger} disabled={running}>
            {running ? "Çalışıyor… (~90s)" : "Karşılaştırmayı Çalıştır"}
          </Button>
        </div>
        {err && <p className="mb-3 text-sm text-destructive">{err}</p>}
        {runs.length > 0 && <MiniLine runs={runs} />}
      </Card>

      <Card className="p-4">
        <h3 className="mb-3 text-base font-semibold">Geçmiş Çalıştırmalar</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                <th className="py-2">Tarih</th>
                <th className="py-2">Sorgu</th>
                <th className="py-2">
                  <Term label="NDCG@10" hint={HINTS.ndcg10} />
                </th>
                <th className="py-2">
                  <Term label="MAP@5" hint={HINTS.map5} />
                </th>
                <th className="py-2">
                  <Term label="MRR@10" hint={HINTS.mrr10} />
                </th>
                <th className="py-2">
                  <Term label="Recall@20" hint={HINTS.recall20} />
                </th>
                <th className="py-2">
                  <Term label="Gecikme" hint="Sorgu başına ortalama süre — p50 / p95 milisaniye" /> p50/p95
                </th>
                <th className="py-2">Tetikleyen</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-b">
                  <td className="py-2 text-xs">
                    {formatTrDateTime(r.started_at)}
                  </td>
                  <td className="py-2">{r.n_queries}</td>
                  <td className="py-2 font-mono">{fmt(r.ndcg_10)}</td>
                  <td className="py-2 font-mono">{fmt(r.map_5)}</td>
                  <td className="py-2 font-mono">{fmt(r.mrr_10)}</td>
                  <td className="py-2 font-mono">{fmt(r.recall_20)}</td>
                  <td className="py-2 font-mono text-xs">
                    {r.latency_ms_p50?.toFixed(0) ?? "—"} /{" "}
                    {r.latency_ms_p95?.toFixed(0) ?? "—"}
                  </td>
                  <td className="py-2 text-xs text-muted-foreground">
                    {r.triggered_by ?? "—"}
                  </td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-6 text-center text-muted-foreground">
                    Henüz çalıştırma yok.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function MiniLine({ runs }: { runs: BenchmarkRunSummary[] }) {
  const reversed = [...runs].reverse(); // eski → yeni
  const ndcg = reversed.map((r) => r.ndcg_10 ?? 0);
  const mrr = reversed.map((r) => r.mrr_10 ?? 0);
  const map5 = reversed.map((r) => r.map_5 ?? 0);

  if (ndcg.length === 0) return null;

  const W = 600;
  const H = 120;
  const PAD = 20;

  const all = [...ndcg, ...mrr, ...map5].filter((n) => n > 0);
  const max = Math.max(...all, 1);
  const min = Math.min(...all, 0);

  const path = (vals: number[]) => {
    if (vals.length === 0) return "";
    const stepX = (W - 2 * PAD) / Math.max(vals.length - 1, 1);
    return vals
      .map((v, i) => {
        const x = PAD + i * stepX;
        const y =
          PAD + (H - 2 * PAD) * (1 - (v - min) / (max - min || 1));
        return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");
  };

  return (
    <div className="mb-2">
      <svg
        width="100%"
        viewBox={`0 0 ${W} ${H}`}
        className="rounded border bg-card"
        role="img"
        aria-label="Karşılaştırma eğilim grafiği"
      >
        <path
          d={path(ndcg)}
          stroke="hsl(220, 80%, 55%)"
          strokeWidth="2"
          fill="none"
        />
        <path
          d={path(mrr)}
          stroke="hsl(140, 60%, 45%)"
          strokeWidth="2"
          fill="none"
        />
        <path
          d={path(map5)}
          stroke="hsl(30, 90%, 55%)"
          strokeWidth="2"
          fill="none"
        />
      </svg>
      <div className="mt-1 flex gap-4 text-xs">
        <Legend color="hsl(220, 80%, 55%)" label="NDCG@10" hint={HINTS.ndcg10} />
        <Legend color="hsl(140, 60%, 45%)" label="MRR@10" hint={HINTS.mrr10} />
        <Legend color="hsl(30, 90%, 55%)" label="MAP@5" hint={HINTS.map5} />
      </div>
    </div>
  );
}

function Legend({
  color,
  label,
  hint,
}: {
  color: string;
  label: string;
  hint?: string;
}) {
  return (
    <span className="flex items-center gap-1">
      <span
        className="inline-block h-2 w-3 rounded-sm"
        style={{ background: color }}
      />
      <span className="text-muted-foreground">
        {hint ? <Term label={label} hint={hint} /> : label}
      </span>
    </span>
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

  if (err) return <p className="text-sm text-destructive">Hata: {err}</p>;
  if (!data)
    return <p className="text-sm text-muted-foreground">Yükleniyor…</p>;

  return (
    <Card className="p-4">
      <h3 className="mb-3 text-base font-semibold">
        Atıf Sağlığı{" "}
        <InfoTooltip content={HINTS.citation} className="ml-1 align-middle" />
        <span className="ml-2 text-sm font-normal text-muted-foreground">
          (son {data.sample_size} üretim)
        </span>
      </h3>
      <div className="grid gap-3 md:grid-cols-2">
        <Metric
          label="Format düzeltmesi (toplam)"
          value={data.repairs_total}
          subtitle="(ID:N), (kaynak:N) → [#N] dönüşümü"
        />
        <Metric
          label="Düzeltme / üretim"
          value={data.repairs_avg_per_gen.toFixed(2)}
          subtitle="ortalama"
        />
        <Metric
          label={
            <Term
              label="Kanıtsız iddia uyarısı"
              hint={HINTS.unsupportedClaim}
            />
          }
          value={data.unsupported_warnings}
          subtitle="hedef <%2"
        />
        <Metric
          label="Kanıtsız iddia / üretim"
          value={data.unsupported_avg_per_gen.toFixed(2)}
        />
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        Atıf doğrulayıcı (#180) cümleleri kaynak embedding cosine ≥ 0.55 ile
        eşleştirir; format düzeltme regex tabanlı.
      </p>
    </Card>
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

  if (err) return <p className="text-sm text-destructive">Hata: {err}</p>;
  if (!data)
    return <p className="text-sm text-muted-foreground">Yükleniyor…</p>;

  return (
    <Card className="p-4">
      <h3 className="mb-3 text-base font-semibold">
        Yeniden Sıralayıcı{" "}
        <InfoTooltip content={HINTS.reranker} className="ml-1 align-middle" />
        <span className="ml-2 text-sm font-normal text-muted-foreground">
          (son 24 saat)
        </span>
      </h3>
      {data.sample_size === 0 ? (
        <p className="text-sm text-muted-foreground">
          Bu pencerede yeniden sıralama çağrısı yok. Trafik geldikçe metric'ler
          dolacak.
        </p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          <Metric label="Çağrı sayısı" value={data.sample_size} />
          <Metric
            label="Ortalama gecikme"
            value={`${data.avg_latency_ms?.toFixed(0) ?? "—"} ms`}
          />
          <Metric
            label={<Term label="Gecikme p50" hint={HINTS.p50} />}
            value={`${data.p50_latency_ms?.toFixed(0) ?? "—"} ms`}
          />
          <Metric
            label={<Term label="Gecikme p95" hint={HINTS.p95} />}
            value={`${data.p95_latency_ms?.toFixed(0) ?? "—"} ms`}
          />
          <KV
            k="Son çağrı"
            v={
              data.last_call_at
                ? formatTrDateTime(data.last_call_at)
                : "—"
            }
          />
        </div>
      )}
    </Card>
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
    <div className="space-y-4">
      <Card className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold">
              RAPTOR-Lite Haftalık Kümeler{" "}
              <InfoTooltip
                content={HINTS.raptor}
                className="ml-1 align-middle"
              />
            </h3>
            <p className="text-xs text-muted-foreground">
              Günlük gündem kartları haftalık tema kart altında gruplanır.
            </p>
          </div>
          <Button onClick={trigger} disabled={running}>
            {running ? "Çalışıyor…" : "Şimdi Oluştur"}
          </Button>
        </div>
        {err && <p className="mb-3 text-sm text-destructive">{err}</p>}
        {trigResult && (
          <p className="mb-3 rounded bg-muted px-3 py-2 text-sm">
            {trigResult.daily_count} günlük → {trigResult.cluster_count} küme
            (başarılı: {trigResult.ok_count})
          </p>
        )}
      </Card>

      <Card className="p-4">
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
            <p className="py-6 text-center text-muted-foreground">
              Henüz haftalık küme yok. Yukarıdaki "Şimdi Oluştur" ile
              tetikleyin.
            </p>
          )}
        </div>
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
    <div className="rounded border p-3">
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
            <Badge>
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
  const [data, setData] = useState<InspectQueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setErr(null);
    try {
      const r = await ragInspectQuery(query, 10, 80, usePlanner);
      setData(r);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <h3 className="mb-3 text-base font-semibold">
          Sorgu İnceleyici{" "}
          <InfoTooltip
            content="Bir sorguyu retrieval pipeline'a gönderir; RRF skorları ile yeniden sıralayıcı skorlarını yan yana gösterir. Kalite hatalarını teşhis için."
            className="ml-1 align-middle"
          />
        </h3>
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
        <label className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={usePlanner}
            onChange={(e) => setUsePlanner(e.target.checked)}
            className="h-3.5 w-3.5"
          />
          <span>
            Query Planner ile zenginleştir{" "}
            <InfoTooltip content="LLM ile sorgudan ana konu + 3-5 keyword çıkar; bunları arama metnine ekle. Kullanıcı tarafındaki gerçek davranışı simüle eder." />
          </span>
        </label>
        {err && <p className="mt-2 text-sm text-destructive">{err}</p>}
      </Card>

      {data?.planner?.used && (
        <Card className="p-4">
          <h4 className="mb-2 text-sm font-semibold">Planner Çıktısı</h4>
          <div className="space-y-1 text-xs">
            <div>
              <span className="text-muted-foreground">Konu:</span>{" "}
              <span className="font-mono">{data.planner.topic_query}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Anahtar kelimeler:</span>{" "}
              {data.planner.keywords.map((k) => (
                <Badge key={k} variant="secondary" className="ml-1">
                  {k}
                </Badge>
              ))}
            </div>
            <div>
              <span className="text-muted-foreground">Zengin sorgu:</span>{" "}
              <code className="rounded bg-muted px-2 py-0.5">{data.planner.enriched_query}</code>
            </div>
          </div>
        </Card>
      )}

      {data && (
        <Card className="p-4">
          <h4 className="mb-3 text-sm font-semibold">
            Yeniden Sıralanmış İlk 10
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                  <th className="py-2">#</th>
                  <th className="py-2">Başlık</th>
                  <th className="py-2">
                    <Term label="RRF" hint={HINTS.rrf} />
                  </th>
                  <th className="py-2">
                    <Term
                      label="Alaka"
                      hint="Cross-encoder ham logit'i sigmoid ile 0-1 aralığına normalize edildi. ≥0.5 güçlü alaka, 0.1-0.5 zayıf, <0.1 alakasız."
                    />
                  </th>
                  <th className="py-2">
                    <Term
                      label="RRF sırası"
                      hint="Yeniden sıralama yapılmasaydı bu sonuç hangi sırada olurdu."
                    />
                  </th>
                  <th className="py-2">
                    <Term
                      label="Δ"
                      hint="Sıralama değişimi. ↑ = cross-encoder yukarı taşıdı, ↓ = aşağı düşürdü."
                    />
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.reranked_top.map((r, i) => {
                  const delta =
                    r.rrf_rank != null ? r.rrf_rank - (i + 1) : null;
                  return (
                    <tr key={r.id} className="border-b">
                      <td className="py-2 font-mono">{i + 1}</td>
                      <td className="py-2">{r.title}</td>
                      <td className="py-2 font-mono text-xs">
                        {r.rrf_score?.toFixed(3) ?? "—"}
                      </td>
                      <td className="py-2">
                        <RerankBadge logit={r.rerank_score} />
                      </td>
                      <td className="py-2 font-mono text-xs">
                        {r.rrf_rank ?? "—"}
                      </td>
                      <td className="py-2 font-mono text-xs">
                        {delta == null ? (
                          "—"
                        ) : (
                          <span
                            className={
                              delta > 0
                                ? "text-emerald-600 dark:text-emerald-400"
                                : delta < 0
                                  ? "text-orange-600"
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
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Δ &gt; 0: yeniden sıralayıcı bu sonucu yukarı taşıdı (kalite kazancı). Δ &lt;
            0: aşağı düşürdü.
          </p>
        </Card>
      )}
    </div>
  );
}

// ============================================================================
// Yardımcı bileşenler
// ============================================================================

function FlagRow({
  label,
  enabled,
}: {
  label: React.ReactNode;
  enabled: boolean;
}) {
  return (
    <div className="flex items-center justify-between rounded border p-2">
      <span className="text-sm">{label}</span>
      <Badge variant={enabled ? "default" : "secondary"}>
        {enabled ? "AÇIK" : "KAPALI"}
      </Badge>
    </div>
  );
}

function KV({ k, v }: { k: React.ReactNode; v: string }) {
  return (
    <div className="flex items-center justify-between rounded border p-2">
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
    <div className="rounded border p-3">
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
  if (score >= 0.5) return <Badge variant="success">{text}</Badge>;
  if (score >= 0.1) return <Badge variant="warning">{text}</Badge>;
  return <Badge variant="muted">{text} · düşük</Badge>;
}
