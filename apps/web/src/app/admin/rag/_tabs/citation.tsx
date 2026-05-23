"use client";

/**
 * Admin RAG sayfası — Atıf (Citation) sekmesi (PR-7b-2).
 *
 * Phase 7b admin/rag mini-plan kapsamında 13 PR sırasının 3. adımı.
 * `CitationTab` + `CitationSkeleton` page.tsx'ten saf taşıma
 * (byte-for-byte korumalı); imza/davranış/JSX/render değişikliği YOK.
 *
 * Tek API çağrısı: `ragCitationStats(100)` — read-only GET
 * `/admin/rag/citation/stats`. State-changing endpoint YOK.
 *
 * "use client" direktifi defensive olarak eklendi (PR-7b-1 deseni).
 *
 * Refs:
 * - wiki/topics/phase7b-admin-rag-mini-plan.md — Phase 7b mini-plan
 * - apps/web/src/app/admin/rag/_shared.tsx — HINTS + StatCard (PR-7b-1)
 * - apps/web/src/app/admin/rag/page.tsx — root router (CitationTab import)
 */

import { useEffect, useState } from "react";

import {
  CitationStatsResponse,
  ragCitationStats,
} from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip, Term } from "@/components/info-tooltip";

import { HINTS, StatCard } from "../_shared";

export function CitationTab() {
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
