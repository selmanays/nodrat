"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Menu } from "lucide-react";

import { ChatInput } from "@/components/chat/ChatInput";
import { ChatMessage } from "@/components/chat/ChatMessage";
import {
  ChatSettingsModal,
  loadChatSettings,
} from "@/components/chat/ChatSettingsModal";
import { ConversationSidebar } from "@/components/chat/ConversationSidebar";
import type {
  DiscoveredSource,
  ThinkingStep,
} from "@/components/chat/ThinkingPanel";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  getChatConversation,
  streamChatMessage,
  type ChatMessage as ChatMessageType,
} from "@/lib/api";

interface StreamingState {
  role: "assistant";
  content: string;
  thinking_steps: ThinkingStep[];
  sources_discovered: DiscoveredSource[];
  is_streaming: boolean;
}

export default function ChatThreadPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const convId = params?.id;
  const initialMessage = searchParams?.get("initial");

  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [title, setTitle] = useState<string>("Sohbet");
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState<StreamingState | null>(null);
  const [sidebarKey, setSidebarKey] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const submittedInitial = useRef(false);

  // 1) Conversation thread'i yükle
  useEffect(() => {
    if (!convId) return;
    let mounted = true;
    setLoading(true);
    getChatConversation(convId)
      .then((thread) => {
        if (!mounted) return;
        setTitle(thread.title);
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
      const userMsg: ChatMessageType = {
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
        const settings = loadChatSettings(convId);

        await streamChatMessage(
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
        const refreshed = await getChatConversation(convId);
        setMessages(refreshed.messages);
        setTitle(refreshed.title);
        setStreaming(null);
        setSidebarKey((k) => k + 1);
      } catch (e: unknown) {
        console.error("stream failed", e);
        setStreaming((prev) =>
          prev ? { ...prev, is_streaming: false } : prev,
        );
        alert(e instanceof Error ? e.message : "Akış hatası");
      }
    },
    [convId],
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

  // 4) Auto-scroll
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, streaming?.content]);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] w-full">
      {/* Desktop sidebar */}
      <ConversationSidebar
        refreshKey={sidebarKey}
        className="hidden md:flex"
      />

      {/* Mobile sidebar — Sheet */}
      <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>Sohbet listesi</SheetTitle>
          </SheetHeader>
          <ConversationSidebar
            refreshKey={sidebarKey}
            className="w-full border-r-0"
            onItemSelect={() => setMobileSidebarOpen(false)}
          />
        </SheetContent>
      </Sheet>

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-border px-3 py-3 md:px-6">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setMobileSidebarOpen(true)}
            aria-label="Sohbet listesini aç"
            className="md:hidden"
          >
            <Menu className="size-4" />
          </Button>
          <h1 className="min-w-0 truncate text-base font-medium">{title}</h1>
        </div>

        <ScrollArea className="flex-1">
          <div
            ref={scrollRef}
            className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6 md:px-6"
          >
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
                  <ChatMessage key={m.id} message={m} />
                ))}
                {streaming && <ChatMessage streaming={streaming} />}
              </>
            )}
          </div>
        </ScrollArea>

        <div className="border-t border-border px-3 py-3 md:px-6 md:py-4">
          <div className="mx-auto max-w-3xl">
            <ChatInput
              placeholder="Devam et veya yeni soru sor..."
              disabled={!!streaming?.is_streaming}
              loading={!!streaming?.is_streaming}
              onSubmit={submitMessage}
              onOpenSettings={() => setSettingsOpen(true)}
            />
          </div>
        </div>

        <ChatSettingsModal
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
          conversationId={convId}
        />
      </main>
    </div>
  );
}
