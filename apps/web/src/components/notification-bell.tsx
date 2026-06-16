"use client";

/**
 * NotificationBell (#1581 C) — /app üst barı bildirim zili + panel.
 *
 * Trend-alert bildirimleri (kullanıcının ilgi kümesindeki entity "Patlıyor").
 * Okunmamış sayısı badge + popover liste + tümünü-okundu. 2dk poll. user-scoped
 * (backend yalnız kendi bildirimleri). Bildirim yoksa/flag OFF → sessiz (0 badge).
 */

import { useCallback, useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  type NotificationItem,
  getMyNotifications,
  markNotificationsRead,
} from "@/lib/api";
import { cn } from "@/lib/utils";

export function NotificationBell() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await getMyNotifications({ limit: 20 });
      setItems(r.notifications);
      setUnread(r.unread_count);
    } catch {
      /* sessiz — zil arka plan, hata kullanıcıyı rahatsız etmesin */
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 120_000); // 2 dk poll
    return () => clearInterval(t);
  }, [load]);

  async function markAll() {
    setBusy(true);
    try {
      const r = await markNotificationsRead();
      setUnread(r.unread_count);
      setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    } catch {
      toast.error("İşaretlenemedi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Popover
      onOpenChange={(o) => {
        if (o) void load();
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label="Bildirimler">
          <Bell className="h-5 w-5" />
          {unread > 0 ? (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium text-white">
              {unread > 9 ? "9+" : unread}
            </span>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <span className="text-sm font-medium">Bildirimler</span>
          {unread > 0 ? (
            <button
              type="button"
              onClick={() => void markAll()}
              disabled={busy}
              className="text-xs text-muted-foreground hover:text-foreground disabled:opacity-50"
            >
              Tümünü okundu işaretle
            </button>
          ) : null}
        </div>
        <div className="max-h-80 overflow-y-auto">
          {items.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">
              Henüz bildirim yok. İlgi alanlarındaki bir konu öne çıkınca burada
              görünecek.
            </p>
          ) : (
            items.map((n) => (
              <div
                key={n.id}
                className={cn(
                  "border-b px-3 py-2.5 last:border-0",
                  !n.read && "bg-accent/40",
                )}
              >
                <p className="text-sm">{n.title}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {new Date(n.created_at).toLocaleString("tr-TR")}
                </p>
              </div>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
