"use client";

/**
 * Admin RAG sayfası — Karşılaştırma (Benchmark) sekmesi (PR-7b-9).
 *
 * Phase 7b admin/rag mini-plan kapsamında 10. PR (9/13 → 10/13). BenchmarkTab
 * sembolünü + `benchmarkChartConfig` tab-local sabitini saf taşıma ile
 * `apps/web/src/app/admin/rag/_tabs/benchmark.tsx` dosyasına çıkardı.
 * Davranış değişikliği YOK; setInterval polling + grace period (#700/#712 B4)
 * + suite filter (#696/#712 B4) tüm state/effect byte-for-byte korunur.
 *
 * API çağrıları:
 * - `ragBenchmarkHistory(20)` — read-only GET `/admin/rag/benchmark/history`
 *   (mount + benchmark sonu sonrası `load()` re-fetch).
 * - `ragBenchmarkStatus()` — read-only GET `/admin/rag/benchmark/status`
 *   (10s'lik setInterval polling running=true iken; #700/#712 B4).
 * - `ragBenchmarkRun(suite, name)` — POST `/admin/rag/benchmark/run`
 *   (state-changing; arka plan job; SADECE "Karşılaştırmayı Çalıştır" tıkı ile).
 *
 * Production smoke'da Karşılaştırma tab'a TIKLANMAZ ve "Karşılaştırmayı
 * Çalıştır" butonuna basılmaz (job: golden eval ~5-10dk + DB write).
 *
 * Tab-local semboller (yalnız bu dosya kullanır):
 * - `benchmarkChartConfig` (ChartConfig — ndcg/map/mrr renkleri).
 *
 * "use client" direktifi defensive olarak eklendi (PR-7b-1..8 deseni).
 *
 * Refs:
 * - wiki/topics/phase7b-admin-rag-mini-plan.md — Phase 7b mini-plan
 * - apps/web/src/app/admin/rag/page.tsx — root router (BenchmarkTab import)
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
  ragBenchmarkHistory,
  ragBenchmarkRun,
  ragBenchmarkStatus,
} from "@/lib/api";
import { formatTrDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
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
import { InfoTooltip, Term } from "@/components/info-tooltip";

import { HINTS, fmt } from "../_shared";

const benchmarkChartConfig = {
  ndcg: { label: "NDCG@10", color: "var(--chart-1)" },
  map: { label: "MAP@5", color: "var(--chart-2)" },
  mrr: { label: "MRR@10", color: "var(--chart-3)" },
} satisfies ChartConfig;

export function BenchmarkTab() {
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
