"use client";

/**
 * ResearchThread — bir araştırma oturumunun (conversation) thread gövdesi.
 *
 * Faz C: `/research/[id]/page.tsx`'ten çıkarıldı → tek-route birleştirmede
 * (`/app/research?c={id}`) homepage tarafından inline render edilir; ayrı
 * route-segment YOK → giriş→stream sayfa-geçişi sıçraması yok. Parent
 * `key={convId}` verir → conversation değişiminde temiz remount (eski
 * `?initial`+manuel-reset kırılganlığı elendi).
 *
 * Sahiplik: messages + streaming + load + submit + auto-scroll. Sidebar/Sheet/
 * settings-modal parent'ta (paylaşımlı). Pivot (her yeni sorgu = yeni conv) →
 * `onStartNew` ile parent'a delege (parent conv oluşturup ?c= günceller).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ResearchInput } from "./ResearchInput";
import { ResearchMessage } from "./ResearchMessage";
import { loadResearchSettings } from "./ResearchSettingsModal";
import type { DiscoveredSource, ThinkingStep } from "./ThinkingPanel";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  getResearchConversation,
  streamResearchMessage,
  type ResearchMessage as ResearchMessageType,
} from "@/lib/api";

interface StreamingState {
  role: "assistant";
  content: string;
  thinking_steps: ThinkingStep[];
  sources_discovered: DiscoveredSource[];
  is_streaming: boolean;
}

export interface ResearchThreadProps {
  convId: string;
  /** Taze conv (idle'dan yeni başlatıldı) için ilk sorgu — auto-submit. URL
   * `?initial` DEĞİL (parent ref ile geçirir); refresh'te null → sadece yükler. */
  initialQuery?: string | null;
  /** Pivot — yeni araştırma (parent conv oluşturup ?c= günceller). */
  onStartNew: (query: string) => void;
  /** Stream bitince sidebar'ı tazele (auto-subscribe küme ekleyebilir). */
  onActivity?: () => void;
  onOpenSettings: () => void;
}

export function ResearchThread({
  convId,
  initialQuery,
  onStartNew,
  onActivity,
  onOpenSettings,
}: ResearchThreadProps) {
  const [messages, setMessages] = useState<ResearchMessageType[]>([]);
  const [title, setTitle] = useState<string>("Araştırma");
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState<StreamingState | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const submittedInitial = useRef(false);

  // 1) Conversation thread'i yükle. Parent key={convId} verdiği için conv
  // değişiminde bileşen REMOUNT olur → manuel state-reset gerekmez.
  useEffect(() => {
    let mounted = true;
    setLoading(true);
    getResearchConversation(convId)
      .then((thread) => {
        if (!mounted) return;
        setTitle(thread.title);
        // Küme-bağı (artifact_id/cluster_*) message üzerinde gelir (history JOIN)
        // → ResearchMessage canvas'ı kendisi render eder.
        setMessages(thread.messages);
      })
      .catch((e: unknown) => {
        if (!mounted) return;
        console.error("thread load failed", e);
      })
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, [convId]);

  // 2) Mesaj gönder + stream (mevcut conv'a)
  const submitMessage = useCallback(
    async (text: string) => {
      const userMsg: ResearchMessageType = {
        id: `tmp-${Date.now()}`,
        role: "user",
        content: text,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);

      setStreaming({
        role: "assistant",
        content: "",
        thinking_steps: [],
        sources_discovered: [],
        is_streaming: true,
      });

      try {
        const settings = loadResearchSettings(convId);
        await streamResearchMessage(
          convId,
          {
            content: text,
            output_type: settings.output_type || undefined,
            tone: settings.tone || null,
            length: settings.length || null,
            max_posts: settings.max_posts,
            style_profile_id: settings.style_profile_id,
            show_sources: settings.show_sources,
          },
          (event, data) => {
            if (event === "artifact") {
              // Faz B — canvas re-fetch sonrası mesajdan render edilir; canlı
              // event yok sayılır (kart done sonrası re-fetch ile gelir).
              return;
            }
            setStreaming((prev) => {
              if (!prev) return prev;
              const next: StreamingState = { ...prev };
              if (event === "thinking_step") {
                next.thinking_steps = [...prev.thinking_steps, data as unknown as ThinkingStep];
              } else if (event === "source_discovered") {
                next.sources_discovered = [
                  ...prev.sources_discovered,
                  data as unknown as DiscoveredSource,
                ];
              } else if (event === "chunk") {
                const delta = (data as { delta?: string }).delta || "";
                next.content = prev.content + delta;
              } else if (event === "done") {
                next.is_streaming = false;
              }
              return next;
            });
          },
        );

        // Stream bitti — DB'den authoritative yenile (message.artifact_id ile kart)
        const refreshed = await getResearchConversation(convId);
        setMessages(refreshed.messages);
        setTitle(refreshed.title);
        setStreaming(null);
        onActivity?.();
      } catch (e: unknown) {
        console.error("stream failed", e);
        setStreaming((prev) => (prev ? { ...prev, is_streaming: false } : prev));
        toast.error(e instanceof Error ? e.message : "Akış hatası");
      }
    },
    [convId, onActivity],
  );

  // 3) initialQuery (taze conv) auto-submit — sadece bir kere
  useEffect(() => {
    if (loading || !initialQuery || submittedInitial.current) return;
    submittedInitial.current = true;
    if (messages.length === 0) submitMessage(initialQuery);
  }, [loading, initialQuery, messages.length, submitMessage]);

  // 4) Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
  }, [messages, streaming?.content]);

  return (
    <>
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-3 md:px-6">
        <h1 className="min-w-0 truncate text-base font-medium">{title}</h1>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6 md:px-6">
          {loading && messages.length === 0 ? (
            <div className="space-y-4">
              {[1, 2].map((i) => (
                <div key={i} className="h-20 animate-pulse rounded-xl bg-muted/40" />
              ))}
            </div>
          ) : (
            <>
              {messages.map((m) => (
                <ResearchMessage key={m.id} message={m} onFollowup={onStartNew} />
              ))}
              {streaming && <ResearchMessage streaming={streaming} />}
            </>
          )}
          <div ref={bottomRef} aria-hidden />
        </div>
      </ScrollArea>

      <div className="shrink-0 border-t border-border px-3 py-3 md:px-6 md:py-4">
        <div className="mx-auto max-w-3xl">
          <ResearchInput
            placeholder="Yeni bir araştırma sorusu sor…"
            disabled={!!streaming?.is_streaming}
            loading={!!streaming?.is_streaming}
            onSubmit={onStartNew}
            onOpenSettings={onOpenSettings}
          />
        </div>
      </div>
    </>
  );
}
