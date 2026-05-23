"use client";

/**
 * Admin RAG sayfası — Sorgu İnceleyici (Inspector) sekmesi (PR-7b-10).
 *
 * Phase 7b admin/rag mini-plan kapsamında 11. PR (10/13 → 11/13). InspectorTab
 * sembolünü + RerankBadge tab-local helper'ını saf taşıma ile
 * `apps/web/src/app/admin/rag/_tabs/inspector.tsx` dosyasına çıkardı.
 * Davranış değişikliği YOK; form state / Query Planner toggle / suite selector
 * / planner çıktısı / timeframe / sufficiency / NER / answer extraction /
 * reranked top-10 tablosu byte-for-byte korunur.
 *
 * API çağrıları:
 * - `ragInspectQuery(query, 10, 80, usePlanner, suite)` — POST
 *   `/admin/rag/inspect` (state-changing değil ama provider çağrısı YAPAR:
 *   embedding + cross-encoder rerank + opsiyonel LLM planner). Production
 *   smoke'da ASLA tetiklenmez.
 *
 * Tab-local semboller (yalnız bu dosya kullanır):
 * - `RerankBadge` (cross-encoder logit → sigmoid 0-1 + renkli rozet helper).
 *
 * "use client" direktifi defensive olarak eklendi (PR-7b-1..9 deseni).
 *
 * Refs:
 * - wiki/topics/phase7b-admin-rag-mini-plan.md — Phase 7b mini-plan
 * - apps/web/src/app/admin/rag/page.tsx — root router (InspectorTab import)
 */

import { useState } from "react";

import {
  InspectQueryResponse,
  ragInspectQuery,
} from "@/lib/api";
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
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { InfoTooltip, Term } from "@/components/info-tooltip";

import { HINTS } from "../_shared";

export function InspectorTab() {
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
