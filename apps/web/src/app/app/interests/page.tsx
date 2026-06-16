"use client";

/**
 * /app/interests — "İlgi Alanların" (#1016 + #1570 A).
 *
 * Kullanıcının araştırma kümeleri (kendi sorgularından türeyen ilgi alanları)
 * + her birinin AYNI entity'sinin CANLI trend durumu (son 24s, korpus-normalize).
 * Talep (senin ilgin) × arz (haberde ne oluyor). user-scoped (yalnız kendi kümen).
 * Salt-okuma; ek LLM yok. trends.enabled OFF → trend rozeti gizli, ilgi yine görünür.
 */

import { useEffect, useState } from "react";
import { Compass, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { TrendStatusBadge } from "@/components/blocks/trend-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
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
          {items.map((it) => (
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
