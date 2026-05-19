"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Archive, MessageSquare, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  archiveResearchConversation,
  listResearchConversations,
  type ResearchConversationItem,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * ConversationSidebar — sol panel, conversation listesi.
 *
 * Her item: title + last_answer_snippet (200 char preview) + zamanı.
 * Active conversation highlight (current URL match).
 * "+ Yeni" butonu → /app/research (homepage).
 *
 * Real-time refresh: parent component yeni conversation oluşturduğunda
 * `refreshKey` prop'unu artırarak listeyi yeniler.
 *
 * Mobile: parent Sheet ile sarmalayıp onItemSelect ile dismiss eder.
 */
export interface ConversationSidebarProps {
  refreshKey?: number;
  className?: string;
  /** Link/yeni-sohbet tıklamasında parent'a haber ver (mobile Sheet dismiss). */
  onItemSelect?: () => void;
}

function formatRelativeTime(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "şimdi";
  if (minutes < 60) return `${minutes}dk önce`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}sa önce`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}g önce`;
  return date.toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
}

export function ConversationSidebar({
  refreshKey = 0,
  className,
  onItemSelect,
}: ConversationSidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [items, setItems] = useState<ResearchConversationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listResearchConversations({ limit: 100 });
      setItems(data.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Yükleme hatası");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh, refreshKey]);

  const activeId = pathname?.startsWith("/app/research/")
    ? pathname.replace("/app/research/", "").split("/")[0]
    : null;

  const handleArchive = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("Bu araştırmayı arşivlemek istiyor musun?")) return;
    try {
      await archiveResearchConversation(id);
      await refresh();
      if (activeId === id) {
        router.push("/app/research");
      }
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Arşivleme başarısız");
    }
  };

  // S1F (#800 / #804): mobile=true ise dış kabuk yok (Sheet/Drawer parent yönetir)
  return (
    <ConversationSidebarShell className={className}>
      <div className="p-3">
        <Link
          href="/app/research"
          prefetch={false}
          onClick={onItemSelect}
        >
          <Button variant="outline" className="w-full justify-start gap-2">
            <Plus className="size-4" />
            Yeni araştırma
          </Button>
        </Link>
      </div>

      <div className="px-3 pb-2 text-xs font-medium text-muted-foreground">
        Araştırma geçmişi
      </div>

      <ScrollArea className="min-h-0 flex-1 px-2 pb-3">
        {loading ? (
          <div className="space-y-2 px-1">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-12 animate-pulse rounded-lg bg-muted/40"
              />
            ))}
          </div>
        ) : error ? (
          <div className="px-2 py-3 text-xs text-destructive">{error}</div>
        ) : items.length === 0 ? (
          <div className="px-2 py-3 text-xs text-muted-foreground">
            Henüz bir araştırma yok. Yukarıdan başlat.
          </div>
        ) : (
          <ul className="space-y-1">
            {items.map((conv) => {
              const isActive = activeId === conv.id;
              return (
                <li key={conv.id}>
                  <Link
                    href={`/app/research/${conv.id}`}
                    prefetch={false}
                    onClick={onItemSelect}
                    className={cn(
                      "group flex items-start gap-2 rounded-lg px-2 py-2 text-sm transition-colors hover:bg-muted/50",
                      isActive && "bg-muted/70",
                    )}
                  >
                    <MessageSquare className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">
                        {conv.title}
                      </div>
                      {conv.last_answer_snippet && (
                        <div className="truncate text-xs text-muted-foreground">
                          {conv.last_answer_snippet}
                        </div>
                      )}
                      <div className="mt-0.5 text-[10px] uppercase tracking-wide text-muted-foreground/70">
                        {formatRelativeTime(conv.updated_at)} ·{" "}
                        {conv.message_count} sorgu
                      </div>
                    </div>
                    <button
                      type="button"
                      aria-label="Arşivle"
                      onClick={(e) => handleArchive(e, conv.id)}
                      className="opacity-0 transition-opacity group-hover:opacity-100"
                    >
                      <Archive className="size-3.5 text-muted-foreground hover:text-foreground" />
                    </button>
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
