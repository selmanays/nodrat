"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Layers, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Sparkline } from "@/components/blocks/sparkline";
import { TrendStatusBadge } from "@/components/blocks/trend-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { type TrendState } from "@/lib/api";
import { type SubscribedCluster, listMyClusters } from "@/lib/api/clusters";
import { cn } from "@/lib/utils";

/**
 * ConversationSidebar — sol panel = KÜME/KART GEÇMİŞİ (sohbet geçmişi DEĞİL).
 *
 * Faz D: vizyon küme-merkezli → sol panel abone olunan kümeleri listeler
 * (listMyClusters), sohbet konuşmalarını değil. Her item: küme adı + tip +
 * canlı trend rozeti + haber-hacmi sparkline; tıklayınca küme detayı
 * (/app/clusters/{id}) = o kümenin içerik-kartı geçmişi. "Yeni araştırma"
 * butonu korunur. Aktif highlight: /app/clusters/{id} yolundayken.
 *
 * Faz E: layout.tsx'e global mount (research/clusters/artifacts ortak). Yeni
 * sorgu sonrası tazeleme decoupled window-event ('nodrat:clusters-refresh') ile
 * (parent ayrı ağaçta). Mobile: parent Sheet + onItemSelect ile dismiss.
 */
export interface ConversationSidebarProps {
  className?: string;
  /** Link/yeni-araştırma tıklamasında parent'a haber ver (mobile Sheet dismiss). */
  onItemSelect?: () => void;
}

const TYPE_LABEL: Record<string, string> = {
  person: "Kişi",
  org: "Kurum",
  place: "Yer",
  event: "Olay",
  topic: "Konu",
};
const TREND_STATES = new Set(["breaking", "developing", "stable", "fading"]);

export function ConversationSidebar({
  className,
  onItemSelect,
}: ConversationSidebarProps) {
  const pathname = usePathname();
  const [items, setItems] = useState<SubscribedCluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listMyClusters();
      setItems(data.clusters);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Yükleme hatası");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Faz E: layout'a global mount edildiğinde research query'si (yeni küme +
  // auto-subscribe) sidebar'ı doğrudan tetikleyemez (ayrı ağaç) → decoupled
  // window-event ile tazele.
  useEffect(() => {
    const handler = () => refresh();
    window.addEventListener("nodrat:clusters-refresh", handler);
    return () => window.removeEventListener("nodrat:clusters-refresh", handler);
  }, [refresh]);

  const activeId = pathname?.startsWith("/app/clusters/")
    ? pathname.replace("/app/clusters/", "").split("/")[0]
    : null;

  return (
    <ConversationSidebarShell className={className}>
      <div className="p-3">
        <Link href="/app/research" prefetch={false} onClick={onItemSelect}>
          <Button variant="outline" className="w-full justify-start gap-2">
            <Plus className="size-4" />
            Yeni araştırma
          </Button>
        </Link>
      </div>

      <div className="px-3 pb-2 text-xs font-medium text-muted-foreground">
        Takip ettiğin kümeler
      </div>

      <ScrollArea className="min-h-0 flex-1 px-2 pb-3">
        {loading ? (
          <div className="space-y-2 px-1">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 animate-pulse rounded-lg bg-muted/40" />
            ))}
          </div>
        ) : error ? (
          <div className="px-2 py-3 text-xs text-destructive">{error}</div>
        ) : items.length === 0 ? (
          <div className="px-2 py-3 text-xs text-muted-foreground">
            Henüz takip ettiğin küme yok. Bir soru sorarak başla.
          </div>
        ) : (
          <ul className="space-y-1">
            {items.map((c) => {
              const isActive = activeId === c.cluster_id;
              return (
                <li key={c.cluster_id}>
                  <Link
                    href={`/app/clusters/${c.cluster_id}?name=${encodeURIComponent(c.canonical_name)}`}
                    prefetch={false}
                    onClick={onItemSelect}
                    className={cn(
                      "flex flex-col gap-1 rounded-lg px-2 py-2 text-sm transition-colors hover:bg-muted/50",
                      isActive && "bg-muted/70",
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <Layers className="size-4 shrink-0 text-muted-foreground" />
                      <span className="truncate text-sm font-medium">
                        {c.canonical_name}
                      </span>
                      <Badge variant="secondary" className="shrink-0 text-[10px]">
                        {TYPE_LABEL[c.cluster_type] ?? c.cluster_type}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2 pl-6">
                      {c.trend_state && TREND_STATES.has(c.trend_state) ? (
                        <TrendStatusBadge state={c.trend_state as TrendState} />
                      ) : (
                        <span className="text-[10px] text-muted-foreground">
                          Şu an sakin
                        </span>
                      )}
                      <Sparkline data={c.spark} className="text-primary/70" />
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </ScrollArea>
    </ConversationSidebarShell>
  );
}

function ConversationSidebarShell({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <aside
      className={cn(
        "flex h-full w-72 flex-col border-r border-border bg-card/40",
        className,
      )}
    >
      {children}
    </aside>
  );
}
