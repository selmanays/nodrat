"use client";

/**
 * Admin RAG Observability Dashboard (#191)
 *
 * Epic #189 — sistem yöneticisi paneli RAG izleme.
 * Tabs: Health / Benchmark / Citation / Reranker / RAPTOR / Inspector
 */

import { useEffect, useState } from "react";
import { Activity, BarChart3, Database, FileSearch, Quote, Sparkles, Zap } from "lucide-react";

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
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

type TabKey = "health" | "benchmark" | "citation" | "rerank" | "raptor" | "inspector";

const TABS: Array<{ key: TabKey; label: string; icon: React.ElementType }> = [
  { key: "health", label: "Health", icon: Activity },
  { key: "benchmark", label: "Benchmark", icon: BarChart3 },
  { key: "citation", label: "Citation", icon: Quote },
  { key: "rerank", label: "Reranker", icon: Zap },
  { key: "raptor", label: "RAPTOR", icon: Database },
  { key: "inspector", label: "Inspector", icon: FileSearch },
];

export default function AdminRagPage() {
  const [tab, setTab] = useState<TabKey>("health");

  return (
    <div className="space-y-6">
      <header className="flex items-center gap-3">
        <Sparkles className="h-7 w-7 text-primary" />
        <div>
          <h1 className="text-2xl font-semibold">RAG Observability</h1>
          <p className="text-sm text-muted-foreground">
            Eval framework, citation validator, reranker ve RAPTOR-Lite durumlarını izle.
          </p>
        </div>
      </header>

      <nav className="flex flex-wrap gap-2 border-b border-border pb-2">
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
// Health
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

  if (loading) return <p className="text-sm text-muted-foreground">Yükleniyor…</p>;
  if (err) return <p className="text-sm text-destructive">Hata: {err}</p>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <h3 className="mb-3 text-base font-semibold">Feature Flags</h3>
        <div className="grid gap-3 md:grid-cols-2">
          <FlagRow label="Reranker" enabled={data.flags.reranker_enabled} />
          <FlagRow label="Local embedding" enabled={data.flags.use_local_embedding} />
          <KV k="Rerank model" v={data.flags.rerank_model} />
          <KV k="Candidate pool" v={String(data.flags.reranker_candidate_pool)} />
        </div>
      </Card>

      <Card className="p-4">
        <h3 className="mb-3 text-base font-semibold">Counts</h3>
        <div className="grid gap-3 md:grid-cols-3">
          <Metric label="Daily cards" value={data.counts.daily_cards} />
          <Metric label="Weekly cards" value={data.counts.weekly_cards} />
          <Metric
            label="Daily with parent"
            value={data.counts.daily_with_parent}
            subtitle="RAPTOR cluster üyeleri"
          />
          <Metric label="Aktif cluster" value={data.counts.active_clusters} />
          <Metric label="Son 24h üretim" value={data.counts.last_24h_generations} />
          <Metric
            label="Insufficient_data"
            value={data.counts.last_24h_insufficient}
            subtitle="son 24 saat"
          />
        </div>
      </Card>

      {data.last_eval ? (
        <Card className="p-4">
          <h3 className="mb-3 text-base font-semibold">Son Eval</h3>
          <p className="mb-2 text-xs text-muted-foreground">
            {data.last_eval.golden_set} ·{" "}
            {data.last_eval.completed_at
              ? new Date(data.last_eval.completed_at).toLocaleString("tr-TR")
              : "—"}
          </p>
          <div className="grid gap-3 md:grid-cols-3">
            <Metric label="NDCG@10" value={fmt(data.last_eval.ndcg_10)} />
            <Metric label="MAP@5" value={fmt(data.last_eval.map_5)} />
            <Metric label="MRR@10" value={fmt(data.last_eval.mrr_10)} />
            <Metric label="Recall@20" value={fmt(data.last_eval.recall_20)} />
            <Metric
              label="Latency p50"
              value={`${data.last_eval.latency_ms_p50?.toFixed(0) ?? "—"} ms`}
            />
            <Metric
              label="Latency p95"
              value={`${data.last_eval.latency_ms_p95?.toFixed(0) ?? "—"} ms`}
            />
          </div>
        </Card>
      ) : (
        <Card className="p-4">
          <p className="text-sm text-muted-foreground">Henüz eval kaydı yok. Benchmark sekmesinden başlatabilirsiniz.</p>
        </Card>
      )}
    </div>
  );
}

// ============================================================================
// Benchmark
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
            <h3 className="text-base font-semibold">Benchmark Trend</h3>
            <p className="text-xs text-muted-foreground">
              Son {runs.length} run NDCG@10 / MAP@5 / MRR@10
            </p>
          </div>
          <Button onClick={trigger} disabled={running}>
            {running ? "Çalışıyor… (~90s)" : "Run benchmark"}
          </Button>
        </div>
        {err && <p className="mb-3 text-sm text-destructive">{err}</p>}
        {runs.length > 0 && <MiniLine runs={runs} />}
      </Card>

      <Card className="p-4">
        <h3 className="mb-3 text-base font-semibold">Eval History</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                <th className="py-2">Tarih</th>
                <th className="py-2">N</th>
                <th className="py-2">NDCG@10</th>
                <th className="py-2">MAP@5</th>
                <th className="py-2">MRR@10</th>
                <th className="py-2">Recall@20</th>
                <th className="py-2">Latency p50/p95</th>
                <th className="py-2">By</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-b">
                  <td className="py-2 text-xs">
                    {new Date(r.started_at).toLocaleString("tr-TR")}
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
                  <td className="py-2 text-xs text-muted-foreground">{r.triggered_by ?? "—"}</td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-6 text-center text-muted-foreground">
                    Henüz run yok.
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
        const y = PAD + (H - 2 * PAD) * (1 - (v - min) / (max - min || 1));
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
      >
        <path d={path(ndcg)} stroke="hsl(220, 80%, 55%)" strokeWidth="2" fill="none" />
        <path d={path(mrr)} stroke="hsl(140, 60%, 45%)" strokeWidth="2" fill="none" />
        <path d={path(map5)} stroke="hsl(30, 90%, 55%)" strokeWidth="2" fill="none" />
      </svg>
      <div className="mt-1 flex gap-4 text-xs">
        <Legend color="hsl(220, 80%, 55%)" label="NDCG@10" />
        <Legend color="hsl(140, 60%, 45%)" label="MRR@10" />
        <Legend color="hsl(30, 90%, 55%)" label="MAP@5" />
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="inline-block h-2 w-3 rounded-sm" style={{ background: color }} />
      <span className="text-muted-foreground">{label}</span>
    </span>
  );
}

// ============================================================================
// Citation
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
  if (!data) return <p className="text-sm text-muted-foreground">Yükleniyor…</p>;

  return (
    <Card className="p-4">
      <h3 className="mb-3 text-base font-semibold">Citation Health (son {data.sample_size} generation)</h3>
      <div className="grid gap-3 md:grid-cols-2">
        <Metric label="Format repair (toplam)" value={data.repairs_total} />
        <Metric
          label="Repair / generation"
          value={data.repairs_avg_per_gen.toFixed(2)}
          subtitle="ortalama"
        />
        <Metric
          label="Unsupported claim warning"
          value={data.unsupported_warnings}
          subtitle="hedef <%2"
        />
        <Metric
          label="Unsupported / generation"
          value={data.unsupported_avg_per_gen.toFixed(2)}
        />
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        Citation validator (#180) cümleleri kanıt cosine ≥0.55 ile eşleştirir; format repair regex tabanlı.
      </p>
    </Card>
  );
}

// ============================================================================
// Reranker
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
  if (!data) return <p className="text-sm text-muted-foreground">Yükleniyor…</p>;

  return (
    <Card className="p-4">
      <h3 className="mb-3 text-base font-semibold">Reranker (son 24 saat)</h3>
      {data.sample_size === 0 ? (
        <p className="text-sm text-muted-foreground">
          Bu pencerede rerank çağrısı yok. Trafik geldikçe metric'ler dolacak.
        </p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          <Metric label="Çağrı sayısı" value={data.sample_size} />
          <Metric
            label="Ortalama latency"
            value={`${data.avg_latency_ms?.toFixed(0) ?? "—"} ms`}
          />
          <Metric
            label="P50 latency"
            value={`${data.p50_latency_ms?.toFixed(0) ?? "—"} ms`}
          />
          <Metric
            label="P95 latency"
            value={`${data.p95_latency_ms?.toFixed(0) ?? "—"} ms`}
          />
          <KV
            k="Son çağrı"
            v={data.last_call_at ? new Date(data.last_call_at).toLocaleString("tr-TR") : "—"}
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
  const [trigResult, setTrigResult] = useState<RaptorTriggerResponse | null>(null);
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
            <h3 className="text-base font-semibold">RAPTOR-Lite Weekly Clusters</h3>
            <p className="text-xs text-muted-foreground">
              Günlük cluster'lar haftalık tema kart altında gruplanır.
            </p>
          </div>
          <Button onClick={trigger} disabled={running}>
            {running ? "Çalışıyor…" : "Build now"}
          </Button>
        </div>
        {err && <p className="mb-3 text-sm text-destructive">{err}</p>}
        {trigResult && (
          <p className="mb-3 rounded bg-muted px-3 py-2 text-sm">
            {trigResult.daily_count} daily → {trigResult.cluster_count} cluster (ok: {trigResult.ok_count})
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
              Henüz weekly cluster yok. Yukarıdaki "Build now" ile tetikleyin.
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
          <Badge variant="secondary">{cluster.daily_children_count} daily</Badge>
          {cluster.importance != null && (
            <Badge>imp {cluster.importance.toFixed(2)}</Badge>
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
// Inspector
// ============================================================================

function InspectorTab() {
  const [query, setQuery] = useState("");
  const [data, setData] = useState<InspectQueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setErr(null);
    try {
      const r = await ragInspectQuery(query, 10);
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
        <h3 className="mb-3 text-base font-semibold">Query Inspector</h3>
        <div className="flex gap-2">
          <Input
            placeholder='örn. "emekli maaşı temmuz zammı"'
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          <Button onClick={submit} disabled={loading || query.trim().length < 2}>
            {loading ? "Çalışıyor…" : "Inspect"}
          </Button>
        </div>
        {err && <p className="mt-2 text-sm text-destructive">{err}</p>}
      </Card>

      {data && (
        <Card className="p-4">
          <h4 className="mb-3 text-sm font-semibold">Reranked Top-K</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                  <th className="py-2">#</th>
                  <th className="py-2">Title</th>
                  <th className="py-2">RRF</th>
                  <th className="py-2">Rerank</th>
                  <th className="py-2">RRF rank</th>
                  <th className="py-2">Δ</th>
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
                      <td className="py-2 font-mono text-xs">
                        {r.rerank_score?.toFixed(3) ?? "—"}
                      </td>
                      <td className="py-2 font-mono text-xs">{r.rrf_rank ?? "—"}</td>
                      <td className="py-2 font-mono text-xs">
                        {delta == null ? (
                          "—"
                        ) : (
                          <span
                            className={
                              delta > 0
                                ? "text-emerald-600"
                                : delta < 0
                                ? "text-orange-600"
                                : "text-muted-foreground"
                            }
                          >
                            {delta > 0 ? `↑${delta}` : delta < 0 ? `↓${-delta}` : "0"}
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
            Δ &gt; 0: cross-encoder daha yukarı taşımış. Δ &lt; 0: aşağı düşürmüş.
          </p>
        </Card>
      )}
    </div>
  );
}

// ============================================================================
// Helpers
// ============================================================================

function FlagRow({ label, enabled }: { label: string; enabled: boolean }) {
  return (
    <div className="flex items-center justify-between rounded border p-2">
      <span className="text-sm">{label}</span>
      <Badge variant={enabled ? "default" : "secondary"}>
        {enabled ? "ON" : "OFF"}
      </Badge>
    </div>
  );
}

function KV({ k, v }: { k: string; v: string }) {
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
  label: string;
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
