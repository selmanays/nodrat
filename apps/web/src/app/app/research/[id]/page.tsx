"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Menu } from "lucide-react";
import { toast } from "sonner";

import { ResearchInput } from "@/components/research/ResearchInput";
import { ResearchMessage } from "@/components/research/ResearchMessage";
import {
  ResearchSettingsModal,
  loadResearchSettings,
} from "@/components/research/ResearchSettingsModal";
import { ConversationSidebar } from "@/components/research/ConversationSidebar";
import type {
  DiscoveredSource,
  ThinkingStep,
} from "@/components/research/ThinkingPanel";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  createResearchConversation,
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

export default function ResearchThreadPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const convId = params?.id;
  const initialMessage = searchParams?.get("initial");

  const [messages, setMessages] = useState<ResearchMessageType[]>([]);
  const [title, setTitle] = useState<string>("Araştırma");
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState<StreamingState | null>(null);
  // Faz B — küme-bağlı artefakt artık MESAJ-TABANLI render edilir (ResearchMessage,
  // message.artifact_id; re-fetch + history JOIN ile gelir). Page-level clusterLink
  // state'i kaldırıldı (cevap=kart: canvas mesajın içinde, ayrı blok değil).
  const [sidebarKey, setSidebarKey] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const submittedInitial = useRef(false);

  // 1) Conversation thread'i yükle
  useEffect(() => {
    if (!convId) return;
    // Next.js App Router aynı dinamik route'ta ([id]) param değişiminde
    // sayfayı REMOUNT ETMEZ → ref/state önceki conversation'dan taşınır.
    // Bağımsız-araştırma akışında /research/A → /research/B geçişinde:
    // submittedInitial sıfırlanmazsa B'nin ?initial= sorgusu HİÇ auto-submit
    // olmaz (boş sayfa). Önceki conv'ın mesaj/stream'i de temizlenir.
    submittedInitial.current = false;
    setMessages([]);
    setStreaming(null);
    let mounted = true;
    setLoading(true);
    getResearchConversation(convId)
      .then((thread) => {
        if (!mounted) return;
        setTitle(thread.title);
        // Küme-bağı (artifact_id/cluster_*) message üzerinde gelir (history JOIN)
        // → ResearchMessage canvas'ı kendisi render eder; ek derive gerekmez.
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

  // 2) Mesaj gönder + stream
  const submitMessage = useCallback(
    async (text: string) => {
      if (!convId) return;

      // Optimistic user msg
      const userMsg: ResearchMessageType = {
        id: `tmp-${Date.now()}`,
        role: "user",
        content: text,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);

      const initStream: StreamingState = {
        role: "assistant",
        content: "",
        thinking_steps: [],
        sources_discovered: [],
        is_streaming: true,
      };
      setStreaming(initStream);

      try {
        // S1D — settings'i sohbet için yükle (per-conv override veya global default)
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
              // Faz B — canvas re-fetch sonrası mesajdan (message.artifact_id)
              // render edilir; canlı event yok sayılır (artefakt henüz commit
              // anında, kart done sonrası re-fetch ile gelir).
              return;
            }
            setStreaming((prev) => {
              if (!prev) return prev;
              const next: StreamingState = { ...prev };
              if (event === "thinking_step") {
                next.thinking_steps = [
                  ...prev.thinking_steps,
                  data as unknown as ThinkingStep,
                ];
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

        // Stream bitti — final messages yenile (DB'den authoritative)
        const refreshed = await getResearchConversation(convId);
        setMessages(refreshed.messages);
        setTitle(refreshed.title);
        setStreaming(null);
        setSidebarKey((k) => k + 1);
      } catch (e: unknown) {
        console.error("stream failed", e);
        setStreaming((prev) =>
          prev ? { ...prev, is_streaming: false } : prev,
        );
        toast.error(e instanceof Error ? e.message : "Akış hatası");
      }
    },
    [convId],
  );

  // Pivot davranışı: her YENİ sorgu = BAĞIMSIZ araştırma oturumu
  // (research-thread DEĞİL). Mevcut oturuma eklenmez; yeni conversation
  // açılır (sidebar'da ayrı araştırma kaydı). Oturumlar-arası bağlam
  // backend'in işi (condense/L1) — frontend görünür thread DAYATMAZ.
  const startNewResearch = useCallback(
    async (text: string) => {
      const t = text.trim();
      if (!t) return;
      try {
        const conv = await createResearchConversation();
        router.push(
          `/app/research/${conv.id}?initial=${encodeURIComponent(t)}`,
        );
      } catch (e: unknown) {
        toast.error(e instanceof Error ? e.message : "Araştırma başlatılamadı");
      }
    },
    [router],
  );

  // 3) Initial query (URL param) auto-submit — sadece bir kere
  useEffect(() => {
    if (loading || !initialMessage || submittedInitial.current) return;
    submittedInitial.current = true;
    // Yükleme bitince ve thread boşsa auto-submit
    if (messages.length === 0) {
      submitMessage(initialMessage);
    }
  }, [loading, initialMessage, messages.length, submitMessage]);

  // 4) Auto-scroll — Radix ScrollArea'da kaydırılabilir eleman Viewport'tur,
  // content div değil; en-alt sentinel'i scrollIntoView ile Viewport'a sür.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
  }, [messages, streaming?.content]);

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Desktop sidebar */}
      <ConversationSidebar
        refreshKey={sidebarKey}
        className="hidden md:flex"
      />

      {/* Mobile sidebar — Sheet */}
      <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>Araştırma listesi</SheetTitle>
          </SheetHeader>
          <ConversationSidebar
            refreshKey={sidebarKey}
            className="w-full border-r-0"
            onItemSelect={() => setMobileSidebarOpen(false)}
          />
        </SheetContent>
      </Sheet>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-3 md:px-6">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setMobileSidebarOpen(true)}
            aria-label="Araştırma listesini aç"
            className="md:hidden"
          >
            <Menu className="size-4" />
          </Button>
          <h1 className="min-w-0 truncate text-base font-medium">{title}</h1>
        </div>

        <ScrollArea className="min-h-0 flex-1">
          <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6 md:px-6">
            {loading && messages.length === 0 ? (
              <div className="space-y-4">
                {[1, 2].map((i) => (
                  <div
                    key={i}
                    className="h-20 animate-pulse rounded-xl bg-muted/40"
                  />
                ))}
              </div>
            ) : (
              <>
                {messages.map((m) => (
                  <ResearchMessage
                    key={m.id}
                    message={m}
                    onFollowup={startNewResearch}
                  />
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
              onSubmit={startNewResearch}
              onOpenSettings={() => setSettingsOpen(true)}
            />
          </div>
        </div>

        <ResearchSettingsModal
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
          conversationId={convId}
        />
      </main>
    </div>
  );
}
