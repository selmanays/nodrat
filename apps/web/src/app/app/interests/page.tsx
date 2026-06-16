"use client";

/**
 * /app/interests — "İlgi Alanların" (#1016 + #1570 A).
 *
 * Kullanıcının araştırma kümeleri (kendi sorgularından türeyen ilgi alanları)
 * + her birinin AYNI entity'sinin CANLI trend durumu (son 24s, korpus-normalize).
 * Talep (senin ilgin) × arz (haberde ne oluyor). user-scoped (yalnız kendi kümen).
 * Salt-okuma; ek LLM yok. trends.enabled OFF → trend rozeti gizli, ilgi yine görünür.
 */

import { useEffect, useMemo, useState } from "react";
import { Compass, Flame, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { TrendStatusBadge } from "@/components/blocks/trend-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  type ApiException,
  type ResearchInterestItem,
  type TrendState,
  getMyResearchInterests,
} from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  person: "Kişi",
  org: "Kurum",
  place: "Yer",
  event: "Olay",
};
const TREND_STATES = new Set(["breaking", "developing", "stable", "fading"]);
// #1575 trend sıralama rütbesi (yüksek = daha hareketli)
const TREND_RANK: Record<string, number> = {
  breaking: 4,
  developing: 3,
  stable: 2,
  fading: 1,
  quiet: 0,
};
const HOT_STATES = new Set(["breaking", "developing"]);
type SortMode = "engagement" | "trend";

function trendRank(it: ResearchInterestItem): number {
  return TREND_RANK[it.trend_state ?? "quiet"] ?? 0;
}

function fmt(n: number): string {
  return n.toLocaleString("tr-TR");
}

function TrendBadge({ item }: { item: ResearchInterestItem }) {
  const s = item.trend_state;
  if (!s || s === "quiet") {
    return <span className="text-xs text-muted-foreground">Şu an sakin</span>;
  }
  if (!TREND_STATES.has(s)) return null;
  return (
    <div className="flex items-center gap-2">
      <TrendStatusBadge state={s as TrendState} />
      {item.article_count_window != null && item.article_count_window > 0 ? (
        <span className="text-xs text-muted-foreground">
          son 24s {fmt(item.article_count_window)} haber
        </span>
      ) : null}
    </div>
  );
}

export default function InterestsPage() {
  const [items, setItems] = useState<ResearchInterestItem[] | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("engagement");

  async function load() {
    setItems(null);
    try {
      const res = await getMyResearchInterests();
      setItems(res.interests);
    } catch (e) {
      toast.error((e as ApiException).message || "İlgi alanları yüklenemedi");
      setItems([]);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  // #1575 — "şu an hareketli" ilgi alanları (breaking/developing) + sıralama
  const hot = useMemo(
    () => (items ?? []).filter((it) => HOT_STATES.has(it.trend_state ?? "")),
    [items],
  );
  const sorted = useMemo(() => {
    const list = [...(items ?? [])];
    if (sortMode === "trend") {
      list.sort(
        (a, b) =>
          trendRank(b) - trendRank(a) ||
          (b.relative_momentum ?? -99) - (a.relative_momentum ?? -99) ||
          (b.article_count_window ?? 0) - (a.article_count_window ?? 0),
      );
    }
    // "engagement": backend zaten item_count desc döndürür → mevcut sıra
    return list;
  }, [items, sortMode]);

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Compass className="h-6 w-6 text-primary" />
            İlgi Alanların
          </h1>
          <p className="text-sm text-muted-foreground">
            Araştırmalarından türeyen ilgi alanların ve her birinin haberlerdeki güncel
            durumu (son 24 saat). Sadece sana özel — başka kullanıcılarla paylaşılmaz.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void load()} disabled={items === null}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Yenile
        </Button>
      </div>

      {items && items.length > 0 ? (
        <div className="space-y-3">
          {hot.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2">
              <Flame className="h-4 w-4 shrink-0 text-amber-500" />
              <span className="text-sm font-medium">Şu an hareketli:</span>
              {hot.map((it) => (
                <Badge key={it.cluster_id} variant="outline" className="font-normal">
                  {it.canonical_name}
                </Badge>
              ))}
            </div>
          ) : null}
          <div className="flex items-center gap-1 text-sm">
            <span className="mr-1 text-muted-foreground">Sırala:</span>
            {(
              [
                ["engagement", "İlgime göre"],
                ["trend", "Şu an hareketli"],
              ] as const
            ).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                onClick={() => setSortMode(mode)}
                className={cn(
                  "rounded-md px-2 py-1 transition-colors",
                  sortMode === mode
                    ? "bg-accent font-medium"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {items === null ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            Henüz bir ilgi alanın oluşmadı. Araştırma yaptıkça (örn. belirli kişi,
            kurum veya olaylar hakkında) ilgi alanların burada birikecek ve haberlerdeki
            güncel durumlarını göreceksin.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {sorted.map((it) => (
            <Card key={it.cluster_id}>
              <CardContent className="flex items-center justify-between gap-4 py-4">
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{it.canonical_name}</span>
                    <Badge variant="secondary" className="shrink-0">
                      {TYPE_LABEL[it.cluster_type] ?? it.cluster_type}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {fmt(it.item_count)} araştırman
                    {it.parent_cluster_id ? " · alt konu" : ""}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <TrendBadge item={it} />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
