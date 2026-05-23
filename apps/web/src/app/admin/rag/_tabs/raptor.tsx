"use client";

/**
 * Admin RAG sayfası — RAPTOR-Lite Haftalık Kümeler sekmesi (PR-7b-8).
 *
 * Phase 7b admin/rag mini-plan kapsamında 13 PR sırasının 9. adımı.
 * `RaptorTab` + `ClusterRow` (2 sembol) page.tsx'ten saf taşıma
 * (byte-for-byte korumalı); imza/davranış/JSX/render değişikliği YOK.
 *
 * API çağrıları:
 * - `ragRaptorClusters(20)` — read-only GET `/admin/rag/raptor/clusters?limit=20`
 *   (useEffect mount + trigger sonrası `load()` re-fetch).
 * - `ragRaptorTrigger()` — POST `/admin/rag/raptor/trigger`
 *   (state-changing; RAPTOR-Lite job; SADECE "Şimdi Oluştur" manuel tıkı ile).
 *
 * Production smoke'da Raptor tab'a TIKLANMAZ ve "Şimdi Oluştur" butonuna
 * basılmaz (job: DB write `research_cluster` + `message_cluster` + DeepSeek
 * summary + embedding cosine compute).
 *
 * Tab-local semboller (yalnız bu dosya kullanır):
 * - `ClusterRow` (saf presentational; props: cluster + expanded + onToggle)
 *
 * "use client" direktifi defensive olarak eklendi (PR-7b-1..7 deseni).
 *
 * Refs:
 * - wiki/topics/phase7b-admin-rag-mini-plan.md — Phase 7b mini-plan
 * - apps/web/src/app/admin/rag/page.tsx — root router (RaptorTab import)
 */

import { useEffect, useState } from "react";

import {
  RaptorClustersResponse,
  RaptorTriggerResponse,
  WeeklyClusterRow,
  ragRaptorClusters,
  ragRaptorTrigger,
} from "@/lib/api";
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
import { InfoTooltip, Term } from "@/components/info-tooltip";

import { HINTS } from "../_shared";

export function RaptorTab() {
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
