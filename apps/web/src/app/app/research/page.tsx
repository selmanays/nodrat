"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ChevronRight, Flame, Layers, Menu } from "lucide-react";

import { ResearchInput } from "@/components/research/ResearchInput";
import { ResearchSettingsModal } from "@/components/research/ResearchSettingsModal";
import { ConversationSidebar } from "@/components/research/ConversationSidebar";
import { Sparkline } from "@/components/blocks/sparkline";
import { TrendStatusBadge } from "@/components/blocks/trend-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { createResearchConversation, type TrendState } from "@/lib/api";
import { type SubscribedCluster, listMyClusters } from "@/lib/api/clusters";

/**
 * Research homepage — Perplexity-style centered input + sidebar.
 *
 * Akış: kullanıcı soru yazıp gönderir → conversation oluştur → /app/research/{id}'ye
 * yönlendir. Stream orada başlar.
 */
const TYPE_LABEL: Record<string, string> = {
  person: "Kişi",
  org: "Kurum",
  place: "Yer",
  event: "Olay",
  topic: "Konu",
};
const TREND_RANK: Record<string, number> = {
  breaking: 4,
  developing: 3,
  stable: 2,
  fading: 1,
  quiet: 0,
};
const HOT_STATES = new Set(["breaking", "developing"]);
const TREND_STATES = new Set(["breaking", "developing", "stable", "fading"]);

export default function ResearchHomePage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [clusters, setClusters] = useState<SubscribedCluster[] | null>(null);

  useEffect(() => {
    listMyClusters()
      .then((res) => setClusters(res.clusters))
      .catch(() => setClusters([]));
  }, []);

  const handleSubmit = async (text: string) => {
    setSubmitting(true);
    try {
      // 1) Conversation oluştur (title boş — ilk mesajdan auto-gen)
      const conv = await createResearchConversation();
      // 2) Yönlendir — query parametresi ile (oradaki page mesajı stream'le)
      const url = `/app/research/${conv.id}?initial=${encodeURIComponent(text)}`;
      router.push(url);
    } catch (e: unknown) {
      setSubmitting(false);
      alert(e instanceof Error ? e.message : "Araştırma başlatılamadı");
    }
  };

  const suggestions = [
    "Bugünkü gündemde ne var?",
    "Çocukların bahis oynamasını engellemeye yönelik çalışma var mı?",
    "Trump'ın son açıklaması nedir?",
    "Türkiye savunma sanayi 2026 ihracat rakamı",
  ];

  // Radar: takip edilen kümeler, hareketli (breaking/developing) önce.
  const sortedClusters = useMemo(() => {
    const list = [...(clusters ?? [])];
    list.sort(
      (a, b) =>
        (TREND_RANK[b.trend_state ?? "quiet"] ?? 0) -
          (TREND_RANK[a.trend_state ?? "quiet"] ?? 0) ||
        (b.relative_momentum ?? -99) - (a.relative_momentum ?? -99),
    );
    return list;
  }, [clusters]);
  const hot = useMemo(
    () => sortedClusters.filter((c) => HOT_STATES.has(c.trend_state ?? "")),
    [sortedClusters],
  );
  const hasClusters = (clusters?.length ?? 0) > 0;

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Desktop sidebar */}
      <ConversationSidebar className="hidden md:flex" />

      {/* Mobile sidebar — Sheet */}
      <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>Araştırma listesi</SheetTitle>
          </SheetHeader>
          <ConversationSidebar
            className="w-full border-r-0"
            onItemSelect={() => setMobileSidebarOpen(false)}
          />
        </SheetContent>
      </Sheet>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Mobile-only top bar: hamburger */}
        <div className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-2 md:hidden">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setMobileSidebarOpen(true)}
            aria-label="Araştırma listesini aç"
          >
            <Menu className="size-4" />
          </Button>
          <span className="text-sm font-medium text-muted-foreground">
            Yeni araştırma
          </span>
        </div>

        <div className="flex min-h-0 flex-1 flex-col items-center overflow-y-auto px-4 py-8 md:px-6 md:py-10">
          <div className="w-full max-w-3xl space-y-8">
            <div className="space-y-2 pt-4 text-center md:pt-8">
              <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
                Bugün ne araştıralım?
              </h1>
              <p className="text-sm text-muted-foreground">
                Türkçe gündemi kaynaklı araştır — sorduğun konu kalıcı bir kümeye
                dönüşür, sen de takip edersin.
              </p>
            </div>

            <ResearchInput
              placeholder="Bir soru sor veya konu belirt..."
              loading={submitting}
              onSubmit={handleSubmit}
              onOpenSettings={() => setSettingsOpen(true)}
              autoFocus
            />

            <ResearchSettingsModal
              open={settingsOpen}
              onOpenChange={setSettingsOpen}
            />

            {/* Radar: takip edilen kümeler (hareketli önce) — yoksa onboarding */}
            {clusters === null ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {[1, 2, 3, 4].map((i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            ) : hasClusters ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="flex items-center gap-2 text-sm font-medium">
                    <Layers className="size-4 text-primary" />
                    Takip ettiğin kümeler
                  </p>
                  <Link
                    href="/app/clusters"
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    Tümü →
                  </Link>
                </div>
                {hot.length > 0 ? (
                  <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2">
                    <Flame className="size-4 shrink-0 text-amber-500" />
                    <span className="text-sm font-medium">Şu an hareketli:</span>
                    {hot.map((c) => (
                      <Badge key={c.cluster_id} variant="outline" className="font-normal">
                        {c.canonical_name}
                      </Badge>
                    ))}
                  </div>
                ) : null}
                <div className="grid gap-2 sm:grid-cols-2">
                  {sortedClusters.map((c) => (
                    <Link
                      key={c.cluster_id}
                      href={`/app/clusters/${c.cluster_id}?name=${encodeURIComponent(c.canonical_name)}`}
                    >
                      <Card className="h-full transition-colors hover:border-primary/40">
                        <CardContent className="flex items-center justify-between gap-2 p-3">
                          <div className="min-w-0 space-y-1">
                            <div className="flex items-center gap-2">
                              <span className="truncate text-sm font-medium">
                                {c.canonical_name}
                              </span>
                              <Badge variant="secondary" className="shrink-0 text-[10px]">
                                {TYPE_LABEL[c.cluster_type] ?? c.cluster_type}
                              </Badge>
                            </div>
                            <div className="flex items-center gap-2">
                              {c.trend_state && TREND_STATES.has(c.trend_state) ? (
                                <TrendStatusBadge state={c.trend_state as TrendState} />
                              ) : (
                                <span className="text-xs text-muted-foreground">Şu an sakin</span>
                              )}
                              <Sparkline data={c.spark} className="text-primary/70" />
                            </div>
                          </div>
                          <ChevronRight
                            className="size-4 shrink-0 text-muted-foreground"
                            aria-hidden="true"
                          />
                        </CardContent>
                      </Card>
                    </Link>
                  ))}
                </div>
              </div>
            ) : (
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
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
