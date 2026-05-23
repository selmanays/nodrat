"use client";

/**
 * Admin RAG sayfası — Yeniden Sıralama (Reranker) sekmesi (PR-7b-3).
 *
 * Phase 7b admin/rag mini-plan kapsamında 13 PR sırasının 4. adımı.
 * `RerankTab` + tab-local `RerankSkeleton` page.tsx'ten saf taşıma
 * (byte-for-byte korumalı); imza/davranış/JSX/render değişikliği YOK.
 *
 * Tek API çağrısı: `ragRerankStats(24)` — read-only GET
 * `/admin/rag/rerank/stats`. State-changing endpoint YOK.
 *
 * "use client" direktifi defensive olarak eklendi (PR-7b-1/7b-2 deseni).
 *
 * Refs:
 * - wiki/topics/phase7b-admin-rag-mini-plan.md — Phase 7b mini-plan
 * - apps/web/src/app/admin/rag/_shared.tsx — HINTS + StatCard + KV (PR-7b-1)
 * - apps/web/src/app/admin/rag/_tabs/citation.tsx — PR-7b-2 deseni
 * - apps/web/src/app/admin/rag/page.tsx — root router (RerankTab import)
 */

import { useEffect, useState } from "react";

import {
  RerankStatsResponse,
  ragRerankStats,
} from "@/lib/api";
import { formatTrDateTime } from "@/lib/format";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip, Term } from "@/components/info-tooltip";

import { HINTS, KV, StatCard } from "../_shared";

export function RerankTab() {
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
