"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Menu } from "lucide-react";

import { ChatInput } from "@/components/chat/ChatInput";
import { ChatSettingsModal } from "@/components/chat/ChatSettingsModal";
import { ConversationSidebar } from "@/components/chat/ConversationSidebar";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { createChatConversation } from "@/lib/api";

/**
 * Chat homepage — Perplexity-style centered input + sidebar.
 *
 * Akış: kullanıcı soru yazıp gönderir → conversation oluştur → /app/chat/{id}'ye
 * yönlendir. Stream orada başlar.
 *
 * Mevcut /app/generate korunur (form-based legacy).
 */
export default function ChatHomePage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const handleSubmit = async (text: string) => {
    setSubmitting(true);
    try {
      // 1) Conversation oluştur (title boş — ilk mesajdan auto-gen)
      const conv = await createChatConversation();
      // 2) Yönlendir — query parametresi ile (oradaki page mesajı stream'le)
      const url = `/app/chat/${conv.id}?initial=${encodeURIComponent(text)}`;
      router.push(url);
    } catch (e: unknown) {
      setSubmitting(false);
      alert(e instanceof Error ? e.message : "Sohbet başlatılamadı");
    }
  };

  const suggestions = [
    "Bugünkü gündemde ne var?",
    "Çocukların bahis oynamasını engellemeye yönelik çalışma var mı?",
    "Trump'ın son açıklaması nedir?",
    "Türkiye savunma sanayi 2026 ihracat rakamı",
  ];

  return (
    <div className="flex h-[calc(100vh-3.5rem)] w-full">
      {/* Desktop sidebar */}
      <ConversationSidebar className="hidden md:flex" />

      {/* Mobile sidebar — Sheet */}
      <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>Sohbet listesi</SheetTitle>
          </SheetHeader>
          <ConversationSidebar
            className="w-full border-r-0"
            onItemSelect={() => setMobileSidebarOpen(false)}
          />
        </SheetContent>
      </Sheet>

      <main className="flex flex-1 flex-col">
        {/* Mobile-only top bar: hamburger */}
        <div className="flex items-center gap-2 border-b border-border px-3 py-2 md:hidden">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setMobileSidebarOpen(true)}
            aria-label="Sohbet listesini aç"
          >
            <Menu className="size-4" />
          </Button>
          <span className="text-sm font-medium text-muted-foreground">
            Yeni sohbet
          </span>
        </div>

        <div className="flex flex-1 flex-col items-center justify-center px-4 py-8 md:px-6 md:py-12">
          <div className="w-full max-w-2xl space-y-8">
            <div className="space-y-2 text-center">
              <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
                Bugün ne araştıralım?
              </h1>
              <p className="text-sm text-muted-foreground">
                Türkçe gündem üzerinde sohbet et. Kaynaklı, çok-kaynaklı sentez.
              </p>
            </div>

            <ChatInput
              placeholder="Bir soru sor veya konu belirt..."
              loading={submitting}
              onSubmit={handleSubmit}
              onOpenSettings={() => setSettingsOpen(true)}
              autoFocus
            />

            <ChatSettingsModal
              open={settingsOpen}
              onOpenChange={setSettingsOpen}
            />

            <div className="space-y-2">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                Önerilen sorular
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {suggestions.map((s) => (
                  <Button
                    key={s}
                    variant="outline"
                    className="h-auto justify-start whitespace-normal text-left text-sm"
                    onClick={() => handleSubmit(s)}
                    disabled={submitting}
                  >
                    {s}
                  </Button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
