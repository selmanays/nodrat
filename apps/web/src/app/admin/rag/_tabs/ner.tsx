"use client";

/**
 * Admin RAG sayfası — NER sekmesi (PR-7b-5).
 *
 * Phase 7b admin/rag mini-plan kapsamında 13 PR sırasının 6. adımı.
 * `NerTab` + tab-local `NerSkeleton` page.tsx'ten saf taşıma (byte-for-byte
 * korumalı); imza/davranış/JSX/render değişikliği YOK.
 *
 * Tek API çağrısı: `ragNerStats()` — read-only GET `/admin/rag/ner/stats`.
 * State-changing endpoint YOK.
 *
 * NER tab'daki "Yenile" butonu state-changing API trigger DEĞİL — sadece
 * `setRefreshKey((k) => k + 1)` ile yerel state'i artırır; bu da
 * `useEffect` `[refreshKey]` dependency'siyle `ragNerStats()` read-only
 * GET'i yeniden çağırır. DB write / provider call / side-effect YOK.
 *
 * "use client" direktifi defensive olarak eklendi (PR-7b-1..4 deseni).
 *
 * Refs:
 * - wiki/topics/phase7b-admin-rag-mini-plan.md — Phase 7b mini-plan
 * - apps/web/src/app/admin/rag/_shared.tsx — StatCard (PR-7b-1)
 * - apps/web/src/app/admin/rag/page.tsx — root router (NerTab import)
 */

import { useEffect, useState } from "react";

import {
  ragNerStats,
  type RagNerStatsResponse,
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
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { InfoTooltip } from "@/components/info-tooltip";

import { StatCard } from "../_shared";

export function NerTab() {
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
