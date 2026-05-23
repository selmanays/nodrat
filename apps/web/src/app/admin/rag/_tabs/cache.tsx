"use client";

/**
 * Admin RAG sayfası — Önbellek (Cache) sekmesi (PR-7b-4).
 *
 * Phase 7b admin/rag mini-plan kapsamında 13 PR sırasının 5. adımı.
 * `CacheTab` page.tsx'ten saf taşıma (byte-for-byte korumalı); imza/davranış/
 * JSX/render değişikliği YOK. Inline `pct` helper Cache-local olarak korunur.
 *
 * Tek API çağrısı: `ragCacheTelemetry(24)` — read-only GET
 * `/admin/rag/cache/telemetry`. State-changing endpoint YOK.
 *
 * "use client" direktifi defensive olarak eklendi (PR-7b-1/2/3 deseni).
 *
 * Notlar:
 * - Ayrı `CacheSkeleton` komponenti YOK — yükleme durumu inline
 *   "Yükleniyor…" Card ile gösterilir.
 * - `_shared.tsx` yüzeyi yalnız `StatCard` — `HINTS`/`KV`/`fmt` kullanılmaz.
 * - `InfoTooltip` / `Term` / `Skeleton` / `formatTrDateTime` ihtiyacı YOK.
 *
 * Refs:
 * - wiki/topics/phase7b-admin-rag-mini-plan.md — Phase 7b mini-plan
 * - apps/web/src/app/admin/rag/_shared.tsx — StatCard (PR-7b-1)
 * - apps/web/src/app/admin/rag/page.tsx — root router (CacheTab import)
 */

import { useEffect, useState } from "react";

import {
  CacheTelemetryResponse,
  ragCacheTelemetry,
} from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { StatCard } from "../_shared";

export function CacheTab() {
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
