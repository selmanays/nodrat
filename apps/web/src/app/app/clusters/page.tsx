"use client";

/**
 * /app/clusters — "Kümelerim" (Faz 4, küme-merkezli abonelik).
 *
 * Kullanıcının AÇIK abone olduğu kümeler + canlı trend durumu. Her küme bir
 * kalıcı takip birimidir (sohbet değil): tıkla → o kümenin geçmiş üretimleri
 * (artefaktlar) + abonelik yönetimi. İlgi Alanların (örtük) sayfasından FARKLI:
 * burası açık abonelikler (user_cluster_subscriptions). Salt-okuma.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronRight, Layers, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { TrendStatusBadge } from "@/components/blocks/trend-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type ApiException, type TrendState } from "@/lib/api";
import {
  type SubscribedCluster,
  listMyClusters,
  unsubscribeCluster,
} from "@/lib/api/clusters";

const TYPE_LABEL: Record<string, string> = {
  person: "Kişi",
  org: "Kurum",
  place: "Yer",
  event: "Olay",
  topic: "Konu",
};
const TREND_STATES = new Set(["breaking", "developing", "stable", "fading"]);

function fmt(n: number): string {
  return n.toLocaleString("tr-TR");
}

function ClusterTrend({ cluster }: { cluster: SubscribedCluster }) {
  const s = cluster.trend_state;
  if (!s || s === "quiet") {
    return <span className="text-xs text-muted-foreground">Şu an sakin</span>;
  }
  if (!TREND_STATES.has(s)) return null;
  return (
    <div className="flex items-center gap-2">
      <TrendStatusBadge state={s as TrendState} />
      {cluster.article_count_window != null && cluster.article_count_window > 0 ? (
        <span className="text-xs text-muted-foreground">
          son 24s {fmt(cluster.article_count_window)} haber
        </span>
      ) : null}
    </div>
  );
}

export default function ClustersPage() {
  const [items, setItems] = useState<SubscribedCluster[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    setItems(null);
    try {
      const res = await listMyClusters();
      setItems(res.clusters);
    } catch (e) {
      toast.error((e as ApiException).message || "Kümeler yüklenemedi");
      setItems([]);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleUnsubscribe(clusterId: string, name: string) {
    setBusyId(clusterId);
    try {
      await unsubscribeCluster(clusterId);
      setItems((prev) => (prev ?? []).filter((c) => c.cluster_id !== clusterId));
      toast.success(`"${name}" kümesinden çıkıldı`);
    } catch (e) {
      toast.error((e as ApiException).message || "Çıkış başarısız");
    } finally {
      setBusyId(null);
    }
  }

  const count = useMemo(() => items?.length ?? 0, [items]);

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Layers className="h-6 w-6 text-primary" />
            Kümelerim
          </h1>
          <p className="text-sm text-muted-foreground">
            Takip ettiğin konular. Her küme kalıcı bir takip birimidir — tıkla, o
            konuda ürettiğin içerikleri gör ve güncel haber durumunu takip et.
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
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : count === 0 ? (
        <Card>
          <CardContent className="space-y-3 py-12 text-center text-sm text-muted-foreground">
            <p>Henüz bir kümeye abone değilsin.</p>
            <p>
              <Link href="/app/research" className="font-medium text-primary underline">
                Araştırma yap
              </Link>{" "}
              — belirli bir kişi, kurum veya konu sorduğunda o küme oluşur ve
              otomatik abone olursun.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {items.map((c) => (
            <Card key={c.cluster_id} className="transition-colors hover:border-primary/40">
              <CardContent className="flex items-center justify-between gap-4 py-4">
                <Link
                  href={`/app/clusters/${c.cluster_id}`}
                  className="flex min-w-0 flex-1 items-center gap-3"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium">{c.canonical_name}</span>
                      <Badge variant="secondary" className="shrink-0">
                        {TYPE_LABEL[c.cluster_type] ?? c.cluster_type}
                      </Badge>
                      {c.parent_cluster_id ? (
                        <Badge variant="outline" className="shrink-0 font-normal">
                          alt konu
                        </Badge>
                      ) : null}
                    </div>
                    <ClusterTrend cluster={c} />
                  </div>
                </Link>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busyId === c.cluster_id}
                    onClick={() => void handleUnsubscribe(c.cluster_id, c.canonical_name)}
                  >
                    Çık
                  </Button>
                  <Link href={`/app/clusters/${c.cluster_id}`} aria-label="Kümeyi aç">
                    <ChevronRight className="h-5 w-5 text-muted-foreground" />
                  </Link>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
