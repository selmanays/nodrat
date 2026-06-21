"use client";

/**
 * ArtifactCanvas — yayınlanabilir içerik kartı editörü (vizyonun kalbi).
 *
 * `artifacts/[id]/page.tsx` gövdesinden çıkarıldı (Faz A) → route-bağımsız,
 * props-tabanlı. İki mod:
 *  - `embedded={false}` (default): tam sayfa kabuğu (plain layout + 'Kümeye dön'
 *    linki) — `/app/artifacts/[id]` route'unda. Tam sayfa Card OLMAZ (preset
 *    idiom: sayfa ≠ kart).
 *  - `embedded={true}`: research thread'in içine gömülü (Faz B) — shadcn <Card>
 *    (size=sm) içeriği "içerik kartı" olarak sunar, parent'ın kolonuna oturur.
 *
 * Sohbet turu DEĞİL: tek canlı metin (head), doğrudan düzenlenir + quick-action
 * butonlarıyla (kısalt / yeniden yaz / uzat / thread'e çevir) LLM ile revize.
 * Her aksiyon yeni revizyon; geçmiş altta. Backend: revise (3b-1) + quick-action (3b-2).
 *
 * shadcn preset (b1VlIttI radix-luma): yalnız kurulu primitive'ler (Card/Badge/
 * Button/Textarea/Collapsible/Skeleton); customization className/variant ile.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  History,
  Loader2,
  Maximize2,
  Minimize2,
  RefreshCw,
  Save,
  Split,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { type ApiException } from "@/lib/api";
import {
  type ArtifactDetail,
  type QuickActionIntent,
  getArtifact,
  quickActionArtifact,
  reviseArtifact,
} from "@/lib/api/clusters";

const INTENT_LABEL: Record<string, string> = {
  initial: "İlk üretim",
  quick_shorter: "Kısaltıldı",
  quick_rewrite: "Yeniden yazıldı",
  quick_longer: "Genişletildi",
  multi_share: "Thread'e çevrildi",
  freetext: "Elle düzenlendi",
  edit: "Elle düzenlendi",
  system: "Sistem",
};

const QUICK_ACTIONS: {
  intent: QuickActionIntent;
  label: string;
  icon: typeof Minimize2;
}[] = [
  { intent: "quick_shorter", label: "Kısalt", icon: Minimize2 },
  { intent: "quick_rewrite", label: "Yeniden yaz", icon: RefreshCw },
  { intent: "quick_longer", label: "Uzat", icon: Maximize2 },
  { intent: "multi_share", label: "Thread'e çevir", icon: Split },
];

function fmtDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("tr-TR", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function headContent(detail: ArtifactDetail): string {
  const head =
    detail.revisions.find((r) => r.revision_seq === detail.head_revision_seq) ??
    detail.revisions[detail.revisions.length - 1];
  return head?.content ?? "";
}

/** Backend hatasını kullanıcı-dostu TR mesaja çevir. Backend zaten cümle döndürdüyse
 * (örn. consent-403, merkezi api.ts fallback ile) onu göster; makine kodu / "HTTP N"
 * ise status'a göre eşle (llm_revisions_disabled / revision_generation_failed sızmasın). */
function actionErrorMessage(e: unknown): string {
  const ex = e as ApiException;
  const m = (ex.message ?? "").trim();
  const isMachineCode = /^[a-z0-9_]+$/.test(m); // snake_case kod, cümle değil
  if (m && !isMachineCode && m !== `HTTP ${ex.status}`) return m;
  if (ex.status === 403) return "Bu özellik şu an kullanılamıyor.";
  if (ex.status === 502) return "İçerik üretilemedi, lütfen tekrar deneyin.";
  if (ex.status === 404) return "İçerik bulunamadı.";
  return "İşlem başarısız, lütfen tekrar deneyin.";
}

export interface ArtifactCanvasProps {
  artifactId: string;
  /** Inline (research thread içine gömülü) mod — Faz B. */
  embedded?: boolean;
}

export function ArtifactCanvas({ artifactId, embedded = false }: ArtifactCanvasProps) {
  const [detail, setDetail] = useState<ArtifactDetail | null>(null);
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState<string | null>(null); // intent veya "save"

  const refresh = useCallback(
    async (opts?: { setEditor?: boolean }) => {
      const d = await getArtifact(artifactId);
      setDetail(d);
      if (opts?.setEditor !== false) setContent(headContent(d));
      return d;
    },
    [artifactId],
  );

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const d = await getArtifact(artifactId);
        if (active) {
          setDetail(d);
          setContent(headContent(d));
        }
      } catch (e) {
        // Ham .message yerine actionErrorMessage → 404 (silinmiş/başkasına ait
        // artefakt) "İçerik bulunamadı.", makine-kodu/"HTTP N" sızmaz.
        if (active) toast.error(actionErrorMessage(e));
      }
    })();
    return () => {
      active = false;
    };
  }, [artifactId]);

  const dirty = useMemo(
    () => detail != null && content.trim() !== headContent(detail).trim(),
    [content, detail],
  );

  async function runQuickAction(intent: QuickActionIntent) {
    setBusy(intent);
    try {
      const res = await quickActionArtifact(artifactId, intent);
      setContent(res.content);
      await refresh({ setEditor: false }); // revizyon listesini tazele, editörü bozma
      toast.success("Yeni sürüm oluşturuldu");
    } catch (e) {
      toast.error(actionErrorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function handleSave() {
    const text = content.trim();
    if (!text) {
      toast.error("İçerik boş olamaz");
      return;
    }
    setBusy("save");
    try {
      await reviseArtifact(artifactId, text, "edit");
      await refresh();
      toast.success("Kaydedildi");
    } catch (e) {
      toast.error(actionErrorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  if (detail === null) {
    if (embedded) {
      return (
        <Card size="sm">
          <CardContent className="space-y-4">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-56 w-full" />
          </CardContent>
        </Card>
      );
    }
    return (
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-8">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const anyBusy = busy !== null;
  const versionLabel =
    detail.head_revision_seq ?? detail.revisions.at(-1)?.revision_seq ?? "—";

  const titleBadges = (
    <>
      <Badge variant="secondary">{detail.artifact_type}</Badge>
      <Badge variant="outline" className="font-normal">
        v{versionLabel}
      </Badge>
    </>
  );

  // Ortak gövde — header HARİÇ (soru + toolbar + dirty ipucu + canvas + kaydet + geçmiş).
  // Fragment → embedded'da CardContent space-y-4, route'ta sayfa space-y-5 uygular.
  const body = (
    <>
      {/* Bu kartı üreten araştırma sorusu (provenance; kart self-contained) — #1699 */}
      {detail.question && (
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground/70">Soru:</span> {detail.question}
        </p>
      )}
      {/* Quick-action toolbar — dirty iken disable (LLM head.content'ten üretir,
          editördeki kaydedilmemiş taslağı görmez + res.content ile ezerdi). */}
      <div className="flex flex-wrap gap-2">
        {QUICK_ACTIONS.map(({ intent, label, icon: Icon }) => (
          <Button
            key={intent}
            variant="outline"
            size="sm"
            disabled={anyBusy || dirty}
            onClick={() => void runQuickAction(intent)}
          >
            {busy === intent ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Icon className="mr-2 h-4 w-4" />
            )}
            {label}
          </Button>
        ))}
      </div>
      {dirty && (
        <p className="text-xs text-amber-600 dark:text-amber-500">
          Kaydedilmemiş değişikliğiniz var. Quick-action&apos;lar kayıtlı sürümü
          yeniden üretir — taslağınızı kaybetmemek için önce <b>Kaydet</b>&apos;e basın
          (ya da değişikliği geri alın).
        </p>
      )}

      {/* Canvas */}
      <Textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        disabled={anyBusy}
        rows={14}
        className="resize-y font-normal leading-relaxed"
        placeholder="İçerik…"
      />

      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {content.length.toLocaleString("tr-TR")} karakter
          {dirty ? " · kaydedilmemiş değişiklik" : ""}
        </span>
        <Button onClick={() => void handleSave()} disabled={!dirty || anyBusy} size="sm">
          {busy === "save" ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Save className="mr-2 h-4 w-4" />
          )}
          Kaydet
        </Button>
      </div>

      {/* Revizyon geçmişi */}
      <Collapsible className="rounded-2xl border">
        <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium">
          <span className="flex items-center gap-2">
            <History className="h-4 w-4 text-muted-foreground" />
            Sürüm geçmişi ({detail.revisions.length})
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-3 border-t px-4 py-3">
          {[...detail.revisions]
            .sort((a, b) => b.revision_seq - a.revision_seq)
            .map((r) => (
              <div key={r.revision_seq} className="space-y-1">
                <div className="flex items-center gap-2 text-xs">
                  <Badge
                    variant={r.revision_seq === detail.head_revision_seq ? "default" : "outline"}
                    className="font-normal"
                  >
                    v{r.revision_seq}
                  </Badge>
                  <span className="text-muted-foreground">
                    {INTENT_LABEL[r.revision_intent] ?? r.revision_intent}
                  </span>
                  <span className="text-muted-foreground">· {fmtDateTime(r.created_at)}</span>
                </div>
                <p className="line-clamp-2 text-xs text-muted-foreground">{r.content}</p>
              </div>
            ))}
        </CollapsibleContent>
      </Collapsible>
    </>
  );

  // Inline (thread içi) — shadcn Card: içerik "içerik kartı" olarak sunulur.
  if (embedded) {
    return (
      <Card
        size="sm"
        className="motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-2 motion-safe:duration-300"
      >
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            İçerik kartı
            {titleBadges}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">{body}</CardContent>
      </Card>
    );
  }

  // Tam sayfa (route) — plain layout (sayfa ≠ Card).
  return (
    <div className="mx-auto max-w-3xl space-y-5 px-4 py-8">
      <div className="space-y-2">
        <Link
          href={`/app/clusters/${detail.cluster_id}`}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Kümeye dön
        </Link>
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight">İçerik kartı</h1>
          {titleBadges}
        </div>
      </div>
      {body}
    </div>
  );
}
