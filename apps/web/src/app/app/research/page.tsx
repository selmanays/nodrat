"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronRight, Flame, Layers } from "lucide-react";
import { toast } from "sonner";

import { ResearchInput } from "@/components/research/ResearchInput";
import { ResearchThread } from "@/components/research/ResearchThread";
import { ResearchSettingsModal } from "@/components/research/ResearchSettingsModal";
import { Sparkline } from "@/components/blocks/sparkline";
import { TrendStatusBadge } from "@/components/blocks/trend-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { createResearchConversation, type TrendState } from "@/lib/api";
import { type SubscribedCluster, listMyClusters } from "@/lib/api/clusters";

/**
 * Research — birleşik tek-route deneyimi (Faz C) + global sol panel (Faz E).
 *
 * Tek route /app/research: `?c={id}` YOKSA giriş (merkezî input + radar);
 * VARSA o conversation'ın thread'i (ResearchThread) INLINE render edilir —
 * route-segment DEĞİŞMEZ → giriş→stream sayfa-geçişi/skeleton sıçraması yok.
 * Soru gönderince conv oluşturulup nav(?c=) (idle→thread push: back idle'a
 * döner; pivot replace: zincir shallow); ilk sorgu pendingRef ile thread'e
 * taşınır (URL `?initial` elendi). Sol panel (küme geçmişi) + mobile Sheet
 * artık layout.tsx'te (Faz E — research/clusters/artifacts ortak); bu sayfa
 * yalnız içeriği (idle/thread + settings modal) render eder.
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

export default function ResearchPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const convId = searchParams?.get("c") ?? null;

  const [settingsOpen, setSettingsOpen] = useState(false);
  // idle (giriş)
  const [submitting, setSubmitting] = useState(false);
  const [clusters, setClusters] = useState<SubscribedCluster[] | null>(null);

  // Taze conv'un ilk sorgusu (URL'siz). nav remount etmediği için ref oturum-içi
  // taşınır; full-refresh'te null → re-stream yok (sadece yükler).
  const pendingRef = useRef<{ id: string; query: string } | null>(null);

  // Radar: yalnız idle'da fetch. Idle'a HER dönüşte (sidebar/logo/nav/back-forward)
  // submitting'i sıfırla → giriş kilidi açılır (success yolunda router nav sonrası
  // unmount olmadan idle'a dönülünce state sızıyordu — tek-route regresyonu).
  useEffect(() => {
    if (convId) return;
    setSubmitting(false);
    let active = true;
    listMyClusters()
      .then((res) => active && setClusters(res.clusters))
      .catch(() => active && setClusters([]));
    return () => {
      active = false;
    };
  }, [convId]);

  // Araştırma başlat (idle input · thread bottom input · öneri · followup) —
  // conv oluştur + aynı route'ta ?c= ile geç (shallow, sayfa-geçişi hissi yok).
  const startResearch = useCallback(
    async (text: string) => {
      const t = text.trim();
      if (!t) return;
      setSubmitting(true);
      // idle→ilk thread: push (browser-back idle'a döner). thread→thread pivot:
      // replace (pivot zinciri shallow; kümeler sidebar'dan erişilir). İkisi de
      // aynı route + searchParam → remount/skeleton sıçraması YOK.
      const isPivot = convId != null;
      try {
        const conv = await createResearchConversation();
        pendingRef.current = { id: conv.id, query: t };
        const url = `/app/research?c=${conv.id}`;
        if (isPivot) router.replace(url, { scroll: false });
        else router.push(url, { scroll: false });
      } catch (e: unknown) {
        setSubmitting(false);
        toast.error(e instanceof Error ? e.message : "Araştırma başlatılamadı");
      }
    },
    [router, convId],
  );

  const initialQuery =
    convId && pendingRef.current?.id === convId ? pendingRef.current.query : null;

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
    <>
      {convId ? (
        <ResearchThread
          key={convId}
          convId={convId}
          initialQuery={initialQuery}
          onStartNew={startResearch}
          // Faz E: sidebar layout'ta (ayrı ağaç) → window-event ile tazele
          onActivity={() =>
            window.dispatchEvent(new Event("nodrat:clusters-refresh"))
          }
          onOpenSettings={() => setSettingsOpen(true)}
        />
      ) : (
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
              onSubmit={startResearch}
              onOpenSettings={() => setSettingsOpen(true)}
              autoFocus
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
                      onClick={() => startResearch(s)}
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
      )}

      <ResearchSettingsModal
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        conversationId={convId ?? undefined}
      />
    </>
  );
}
