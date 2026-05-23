"use client";

/**
 * Admin RAG sayfası — Sağlık (Health) sekmesi (PR-7b-6).
 *
 * Phase 7b admin/rag mini-plan kapsamında 13 PR sırasının 7. adımı.
 * `HealthTab` + tab-local `HealthSkeleton` + `FlagRow` + `Metric` page.tsx'ten
 * saf taşıma (byte-for-byte korumalı); imza/davranış/JSX/render değişikliği YOK.
 *
 * Tek API çağrısı: `ragHealth()` — read-only GET `/admin/rag/health`.
 * State-changing endpoint YOK.
 *
 * Polling pattern (byte-for-byte korunmuş):
 * - `setInterval(load, 30000)` — her 30 saniyede bir read-only GET yeniden
 *   çağrılır.
 * - `mounted` flag — unmount sonrası state update'leri engeller (React 18
 *   race condition guard).
 * - `clearInterval(t)` + `mounted = false` cleanup return.
 *
 * "use client" direktifi defensive olarak eklendi (PR-7b-1..5 deseni).
 *
 * Tab-local helpers (page.tsx dışında YALNIZ bu dosya kullanır):
 * - `HealthSkeleton` — loading durumu (6 StatCard + 1 detay Card)
 * - `FlagRow` — toggle (Switch disabled) + "AÇIK"/"KAPALI" rozet
 * - `Metric` — küçük metric card (label + mono value + opsiyonel subtitle)
 *
 * Refs:
 * - wiki/topics/phase7b-admin-rag-mini-plan.md — Phase 7b mini-plan
 * - apps/web/src/app/admin/rag/_shared.tsx — HINTS + StatCard + KV + fmt (PR-7b-1)
 * - apps/web/src/app/admin/rag/page.tsx — root router (HealthTab import)
 */

import { useEffect, useState } from "react";

import {
  ragHealth,
  type RagHealthResponse,
} from "@/lib/api";
import { formatTrDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Term } from "@/components/info-tooltip";

import { HINTS, KV, StatCard, fmt } from "../_shared";

export function HealthTab() {
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
