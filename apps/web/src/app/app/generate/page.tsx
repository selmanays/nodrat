"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Bookmark,
  Bot,
  Calendar,
  Copy,
  ExternalLink,
  Flag,
  Loader2,
  Pencil,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiException,
  flagHalu,
  saveGeneration,
  type GenerateMode,
  type GenerateRequest,
  type GenerateResponse,
} from "@/lib/api";
import { formatTrDate } from "@/lib/format";
import {
  isPaywallRequired,
  listStyleProfiles,
} from "@/lib/style-profiles-api";
import { useGenerationStream } from "@/hooks/use-generation-stream";

// Research-driven örnek prompt'lar (validation/research-findings.md)
const SAMPLE_PROMPTS = [
  "Bu hafta yapay zeka regülasyonlarıyla ilgili 3 X paylaşımı üret",
  "Türkiye ekonomisinde son gelişmeler — analitik tonla",
  "Süper Lig'in son haftası, eleştirel ton",
  "Geçen ay vs bu ay sağlık politikaları kıyas",
  "Bugünkü deprem haberleri, kurumsal ton",
];

const MODE_LABEL: Record<GenerateMode, string> = {
  current: "Güncel (bugün)",
  weekly: "Son 7-14 gün",
  archive: "Arşiv (geçmiş gündem)",
};

const MODE_ORDER: GenerateMode[] = ["current", "weekly", "archive"];

/**
 * Suggestion'ı 3 kategoriden birine sınıflar (#79):
 *   - "scope":   konuyu/kapsamı genişletmek (Search)
 *   - "time":    zaman aralığı/dönem (Calendar)
 *   - "fallback": standalone (ChatGPT/Claude) önerisi (Bot)
 *
 * Backend kategorilenmiş alan döndürene kadar (#TODO contract update),
 * basit Türkçe heuristic ile lokal sınıflama yapıyoruz.
 */
type SuggestionCategory = "scope" | "time" | "fallback";

function classifySuggestion(text: string): SuggestionCategory {
  const lower = text.toLocaleLowerCase("tr-TR");
  if (
    lower.includes("chatgpt") ||
    lower.includes("claude") ||
    lower.includes("standalone") ||
    lower.includes("genel bilgi") ||
    lower.includes("kaynaksız")
  ) {
    return "fallback";
  }
  if (
    lower.includes("zaman") ||
    lower.includes("aralık") ||
    lower.includes("hafta") ||
    lower.includes("gün") ||
    lower.includes("dönem") ||
    lower.includes("ay") ||
    lower.includes("tarih") ||
    lower.includes("son ") ||
    lower.includes("geçen") ||
    lower.includes("güncel")
  ) {
    return "time";
  }
  return "scope";
}

const CATEGORY_META: Record<
  SuggestionCategory,
  {
    label: string;
    icon: typeof Search;
    border: string;
    iconColor: string;
    bg: string;
  }
> = {
  scope: {
    label: "Kapsam genişletme",
    icon: Search,
    border: "border-l-info",
    iconColor: "text-info",
    bg: "bg-info/5",
  },
  time: {
    label: "Zaman aralığı",
    icon: Calendar,
    border: "border-l-success",
    iconColor: "text-success",
    bg: "bg-success/5",
  },
  fallback: {
    label: "Standalone alternatif",
    icon: Bot,
    border: "border-l-accent-500",
    iconColor: "text-accent-700",
    bg: "bg-accent-50",
  },
};


export default function GeneratePage() {
  const [requestText, setRequestText] = useState("");
  // #548 — null = "Otomatik" (planner karar verir); sayı = kullanıcı bilinçli
  const [maxPosts, setMaxPosts] = useState<number | null>(null);
  const [tone, setTone] = useState<string>("");
  const [mode, setMode] = useState<GenerateMode | "">("");
  // #73 #74 — output type + length
  const [outputType, setOutputType] = useState<string>("");
  const [length, setLength] = useState<string>("");
  // #52 — Faz 5 stil profili seçimi (Pro+ tier)
  const [styleProfileId, setStyleProfileId] = useState<string>("");
  const [readyStyleProfiles, setReadyStyleProfiles] = useState<
    { id: string; name: string }[]
  >([]);
  const [styleProfilesAvailable, setStyleProfilesAvailable] = useState<
    "loading" | "available" | "paywall" | "empty"
  >("loading");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const requestRef = useRef<HTMLTextAreaElement | null>(null);
  const stream = useGenerationStream();
  const streamState = stream.state;

  // #52 — load ready style profiles (silently degrade for Free/Starter)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await listStyleProfiles();
        if (cancelled) return;
        const ready = resp.data
          .filter((p) => p.status === "ready")
          .map((p) => ({ id: p.id, name: p.name }));
        setReadyStyleProfiles(ready);
        setStyleProfilesAvailable(ready.length > 0 ? "available" : "empty");
      } catch (err) {
        if (cancelled) return;
        if (isPaywallRequired(err)) {
          setStyleProfilesAvailable("paywall");
        } else {
          setStyleProfilesAvailable("empty");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function runGenerate(payload: GenerateRequest) {
    setSubmitting(true);
    setResult(null);
    stream.reset();

    await stream.start(payload);

    setSubmitting(false);
    // Stream tamamlandı — useEffect aşağıda streamState.stage değişimini izleyip
    // result/toast'u kuruyor (closure stale problem'i için).
  }

  // Stream tamamlandığında result state'ini sentezle (save/flag/copy için)
  useEffect(() => {
    if (streamState.stage === "done" && streamState.generationId) {
      const synthesized: GenerateResponse = {
        id: streamState.generationId,
        status: "completed",
        request_text: requestText.trim() || streamState.topicQuery || "",
        mode: (streamState.mode as GenerateMode) || "current",
        output_type: streamState.outputType || "x_post",
        tone: streamState.tone,
        posts: streamState.posts.map((p) => ({
          text: p.text,
          angle: p.angle,
          char_count: p.char_count,
          related_agenda_card_ids: p.related_agenda_card_ids,
        })),
        summary: streamState.summary,
        sources: streamState.sources,
        warnings: streamState.warnings,
        suggestions: [],
        summary_doc_title: streamState.summaryDocTitle,
        summary_doc_items: streamState.summaryDocItems,
        suggested_image: streamState.suggestedImage,
        cost_usd: streamState.costUsd,
        created_at: new Date().toISOString(),
        completed_at: new Date().toISOString(),
      };
      setResult(synthesized);
      if (
        synthesized.summary_doc_items &&
        synthesized.summary_doc_items.length > 0
      ) {
        toast.success(
          `${synthesized.summary_doc_items.length} maddelik özet üretildi`,
        );
      } else {
        toast.success(`${synthesized.posts.length} paylaşım üretildi`);
      }
    } else if (streamState.stage === "error" && streamState.error) {
      const err = streamState.error;
      if (err.code === "QUOTA_EXCEEDED") {
        toast.error(`Kotanız doldu. ${err.reason || ""}`);
      } else if (
        err.code === "INSUFFICIENT_DATA" &&
        streamState.generationId
      ) {
        const synthesized: GenerateResponse = {
          id: streamState.generationId,
          status: "insufficient_data",
          request_text: requestText.trim(),
          mode: (streamState.mode as GenerateMode) || "current",
          output_type: streamState.outputType || "x_post",
          tone: streamState.tone,
          posts: [],
          summary: "",
          sources: [],
          warnings: [err.reason],
          suggestions: err.suggestions || [],
          summary_doc_title: "",
          summary_doc_items: [],
          suggested_image: null,
          cost_usd: 0,
          created_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
        };
        setResult(synthesized);
        toast.warning("Yeterli kaynak yok — alternatif öneriler aşağıda");
      } else {
        toast.error(err.title || "Üretim başarısız");
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamState.stage]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!requestText.trim() || requestText.trim().length < 5) {
      toast.error("İstek en az 5 karakter olmalı");
      return;
    }

    await runGenerate({
      request_text: requestText.trim(),
      max_posts: maxPosts ?? undefined,
      tone: tone || undefined,
      length: length || undefined,
      output_type: outputType || undefined,
      mode_hint: mode || undefined,
      style_profile_id: styleProfileId || undefined,
    });
  }

  /** Aynı request'i farklı mode_hint ile yeniden çalıştırır (#79). */
  async function handleRetryWithMode(newMode: GenerateMode) {
    if (!requestText.trim()) {
      toast.error("İstek boş — tekrar denemek için doldur");
      return;
    }
    setMode(newMode);
    toast.message(`Yeniden deneniyor: ${MODE_LABEL[newMode]}`);
    await runGenerate({
      request_text: requestText.trim(),
      max_posts: maxPosts ?? undefined,
      tone: tone || undefined,
      length: length || undefined,
      output_type: outputType || undefined,
      mode_hint: newMode,
      style_profile_id: styleProfileId || undefined,
    });
  }

  /**
   * "Standalone'a aktar": request_text'i panoya kopyalar ve ChatGPT'yi
   * yeni sekmede açar (kullanıcı yapıştırıp gönderir).
   */
  function handleHandoffToChatGPT() {
    const text = requestText.trim();
    if (!text) {
      toast.error("Aktarılacak istek boş");
      return;
    }
    if (typeof window === "undefined") return;

    navigator.clipboard
      .writeText(text)
      .then(() => toast.success("İstek panoya kopyalandı"))
      .catch(() => toast.warning("Pano izni yok — istek manuel kopyalanmalı"));

    window.open("https://chat.openai.com/", "_blank", "noopener,noreferrer");
  }

  /** "İsteği düzenle": sol panele scroll + textarea'ya focus. */
  function handleEditRequest() {
    if (typeof window === "undefined") return;
    const el = requestRef.current;
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.focus();
    }
  }

  async function handleSave() {
    if (!result) return;
    try {
      await saveGeneration(result.id);
      toast.success("Kaydedildi");
    } catch (error) {
      const apiError = error as ApiException;
      toast.error(apiError.message || "Kayıt başarısız");
    }
  }

  async function handleFlagHalu() {
    if (!result) return;
    const reason = window.prompt("Halüsinasyon detayı (opsiyonel):");
    try {
      await flagHalu(result.id, reason || undefined);
      toast.success("Bildirildi — incelenecek");
    } catch (error) {
      const apiError = error as ApiException;
      toast.error(apiError.message || "Bildirim başarısız");
    }
  }

  function copyPost(text: string) {
    navigator.clipboard.writeText(text).then(
      () => toast.success("Panoya kopyalandı"),
      () => toast.error("Kopyalama başarısız"),
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
      {/* Sol: form */}
      <Card className="lg:sticky lg:top-6 self-start">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-accent-500" />
            Yeni üretim
          </CardTitle>
          <CardDescription>
            Türkçe gündemden kaynaklı X paylaşımı üret. Halüsinasyon korumalı.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="request">Ne üretelim?</Label>
              <Textarea
                id="request"
                ref={requestRef}
                value={requestText}
                onChange={(e) => setRequestText(e.target.value)}
                placeholder="Örn: Bu hafta yapay zeka regülasyonlarıyla ilgili 3 X paylaşımı üret"
                rows={4}
                maxLength={2000}
              />
              <p className="text-xs text-muted-foreground">
                {requestText.length}/2000 karakter
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="max_posts">Paylaşım adedi</Label>
                <Select
                  value={maxPosts === null ? "auto" : String(maxPosts)}
                  onValueChange={(v) =>
                    setMaxPosts(v === "auto" ? null : parseInt(v))
                  }
                >
                  <SelectTrigger id="max_posts" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Otomatik</SelectItem>
                    {[1, 3, 5, 7, 10].map((n) => (
                      <SelectItem key={n} value={String(n)}>
                        {n}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="tone">Ton (opsiyonel)</Label>
                <Select value={tone || "auto"} onValueChange={(v) => setTone(v === "auto" ? "" : v)}>
                  <SelectTrigger id="tone" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Otomatik</SelectItem>
                    <SelectItem value="tarafsız">Tarafsız</SelectItem>
                    <SelectItem value="eleştirel">Eleştirel</SelectItem>
                    <SelectItem value="mizahi">Mizahi</SelectItem>
                    <SelectItem value="kurumsal">Kurumsal</SelectItem>
                    <SelectItem value="aktivist">Aktivist</SelectItem>
                    <SelectItem value="analitik">Analitik</SelectItem>
                    <SelectItem value="sade">Sade</SelectItem>
                    <SelectItem value="sert">Sert</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="output_type">Çıktı türü</Label>
                <Select
                  value={outputType || "auto"}
                  onValueChange={(v) => setOutputType(v === "auto" ? "" : v)}
                >
                  <SelectTrigger id="output_type" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Otomatik</SelectItem>
                    <SelectItem value="x_post">X paylaşımları</SelectItem>
                    <SelectItem value="thread">X thread (numaralı)</SelectItem>
                    <SelectItem value="summary">Özet (madde madde)</SelectItem>
                    <SelectItem value="headline">Headline önerileri</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="length">Uzunluk</Label>
                <Select
                  value={length || "auto"}
                  onValueChange={(v) => setLength(v === "auto" ? "" : v)}
                >
                  <SelectTrigger id="length" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Otomatik</SelectItem>
                    <SelectItem value="short">Kısa</SelectItem>
                    <SelectItem value="medium">Orta</SelectItem>
                    <SelectItem value="long">Uzun</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 sm:col-span-2 lg:col-span-1">
                <Label htmlFor="style_profile">Stil profili (Pro+)</Label>
                {styleProfilesAvailable === "paywall" ? (
                  <div className="rounded-md border border-dashed p-2 text-xs text-muted-foreground">
                    Pro tier'da{" "}
                    <Link
                      href="/app/billing"
                      className="text-primary underline"
                    >
                      açılır
                    </Link>
                  </div>
                ) : styleProfilesAvailable === "empty" ? (
                  <div className="rounded-md border border-dashed p-2 text-xs text-muted-foreground">
                    Henüz hazır profil yok —{" "}
                    <Link
                      href="/app/style-profiles"
                      className="text-primary underline"
                    >
                      oluştur
                    </Link>
                  </div>
                ) : (
                  <Select
                    value={styleProfileId || "none"}
                    onValueChange={(v) =>
                      setStyleProfileId(v === "none" ? "" : v)
                    }
                    disabled={styleProfilesAvailable === "loading"}
                  >
                    <SelectTrigger id="style_profile" className="w-full">
                      <SelectValue
                        placeholder={
                          styleProfilesAvailable === "loading"
                            ? "Yükleniyor…"
                            : "Profil seç"
                        }
                      />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Stil yok (varsayılan)</SelectItem>
                      {readyStyleProfiles.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>

            <Button type="submit" className="w-full" disabled={submitting} variant="default">
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              {submitting ? streamingButtonLabel(streamState.stage) : "Üret"}
            </Button>
          </form>

          {/* Örnek prompt'lar */}
          <div className="mt-6 space-y-2 border-t pt-4">
            <p className="text-xs font-medium text-muted-foreground">
              ÖRNEKLER
            </p>
            {SAMPLE_PROMPTS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setRequestText(p)}
                className="block w-full rounded-md border bg-muted/30 px-3 py-2 text-left text-xs hover:bg-muted"
              >
                {p}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Sağ: result */}
      <div className="space-y-4">
        {/* Streaming live preview (#527) — posts geldikçe güncellenir */}
        {streamState.isStreaming && (
          <StreamingPreview state={streamState} />
        )}

        {!result && !streamState.isStreaming && (
          <Card>
            <CardContent className="py-16 text-center text-sm text-muted-foreground">
              Sol panelde isteğini yaz ve "Üret" butonuna bas.
              <br />
              Sonuçlar burada görünecek.
            </CardContent>
          </Card>
        )}

        {result && result.status === "insufficient_data" && (
          <Card className="border-amber-200 bg-amber-50 dark:bg-amber-950/30">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-amber-900 dark:text-amber-100">
                <AlertTriangle className="h-5 w-5" />
                Yeterli kaynak yok
              </CardTitle>
              <CardDescription className="text-amber-800 dark:text-amber-200">
                Nodrat halüsinasyon riskine karşı kaynak yetersizse içerik
                üretmez. Bu üretim quota&apos;ndan düşmedi.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Kategorize suggestions */}
              {result.suggestions.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">Önerilerimiz</p>
                  <ul className="space-y-2">
                    {result.suggestions.map((s, i) => {
                      const cat = classifySuggestion(s);
                      const meta = CATEGORY_META[cat];
                      const Icon = meta.icon;
                      return (
                        <li
                          key={i}
                          className={`flex items-start gap-3 rounded-md border border-l-4 ${meta.border} ${meta.bg} p-3 text-sm`}
                        >
                          <Icon
                            aria-hidden="true"
                            className={`h-4 w-4 mt-0.5 flex-shrink-0 ${meta.iconColor}`}
                          />
                          <div className="space-y-0.5">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                              {meta.label}
                            </p>
                            <p className="text-foreground">{s}</p>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              {/* Action buttons row */}
              <div className="space-y-3 border-t border-amber-200 pt-4 dark:border-amber-900">
                <p className="text-sm font-medium">Şimdi ne yapmak istersin?</p>

                {/* Mode switcher — tek tıkla yeniden submit */}
                <div className="space-y-2">
                  <Label
                    htmlFor="retry_mode"
                    className="flex items-center gap-1.5 text-xs text-muted-foreground"
                  >
                    <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
                    Modu değiştirip yeniden dene
                  </Label>
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <select
                      id="retry_mode"
                      value=""
                      disabled={submitting}
                      onChange={(e) => {
                        const v = e.target.value as GenerateMode | "";
                        if (v) {
                          void handleRetryWithMode(v);
                        }
                      }}
                      className="flex h-10 w-full flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm disabled:opacity-50"
                    >
                      <option value="">
                        {submitting ? "Yeniden deneniyor…" : "Bir mod seç…"}
                      </option>
                      {MODE_ORDER.filter((m) => m !== mode).map((m) => (
                        <option key={m} value={m}>
                          {MODE_LABEL[m]}
                        </option>
                      ))}
                    </select>
                  </div>
                  {mode && (
                    <p className="text-xs text-muted-foreground">
                      Şu anki mod: <span className="font-medium">{MODE_LABEL[mode]}</span>
                    </p>
                  )}
                </div>

                {/* Edit + ChatGPT handoff */}
                <div className="grid gap-2 sm:grid-cols-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleEditRequest}
                    disabled={submitting}
                  >
                    <Pencil aria-hidden="true" className="h-3.5 w-3.5" />
                    İsteği düzenle
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleHandoffToChatGPT}
                    disabled={submitting}
                    className="border-accent-300 text-accent-900 hover:bg-accent-50"
                  >
                    <Bot aria-hidden="true" className="h-3.5 w-3.5" />
                    Standalone&apos;a aktar
                  </Button>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Standalone seçeneği isteği panoya kopyalar ve ChatGPT&apos;yi
                  yeni sekmede açar.
                </p>
              </div>

              {result.warnings.length > 0 && (
                <p className="border-t border-amber-200 pt-3 text-xs text-muted-foreground dark:border-amber-900">
                  {result.warnings.join("; ")}
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {result && result.status === "completed" && (
          <>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Badge variant="secondary">Tamamlandı</Badge>
                <Badge variant="outline">{result.mode}</Badge>
                <Badge variant="outline">{result.output_type}</Badge>
                {result.tone && <Badge variant="outline">{result.tone}</Badge>}
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={handleSave}>
                  <Bookmark className="h-3.5 w-3.5" />
                  Kaydet
                </Button>
                <Button variant="ghost" size="sm" onClick={handleFlagHalu}>
                  <Flag className="h-3.5 w-3.5" />
                  Halüsinasyon bildir
                </Button>
              </div>
            </div>

            {/* #173 PR-F — Summary mode (multi-item bullet doc) */}
            {result.summary_doc_items && result.summary_doc_items.length > 0 ? (
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <CardTitle className="text-lg">
                      {result.summary_doc_title || "Özet"}
                    </CardTitle>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        const md = `# ${result.summary_doc_title}\n\n${result.summary_doc_items
                          .map(
                            (it, i) =>
                              `${i + 1}. **${it.event}**\n   - Kaynak: ${it.source}${it.date ? ` · Tarih: ${it.date}` : ""}`,
                          )
                          .join("\n\n")}`;
                        navigator.clipboard.writeText(md);
                        toast.success("Özet markdown olarak kopyalandı");
                      }}
                    >
                      <Copy className="h-3.5 w-3.5" />
                      Markdown kopyala
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <ol className="space-y-3">
                    {result.summary_doc_items.map((item, idx) => (
                      <li key={idx} className="flex gap-3">
                        <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-primary dark:bg-muted ">
                          {idx + 1}
                        </span>
                        <div className="flex-1 space-y-1">
                          <p className="text-sm leading-relaxed">{item.event}</p>
                          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                            {item.source && (
                              <Badge variant="outline" className="text-[10px]">
                                {item.source}
                              </Badge>
                            )}
                            {item.date && item.date !== "bilinmiyor" && (
                              <span title={`UTC: ${item.date}`}>
                                {formatTrDate(item.date)}
                              </span>
                            )}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ol>
                </CardContent>
              </Card>
            ) : (
              /* x_post mode (default) */
              <div className="space-y-3">
                {result.posts.map((post, idx) => (
                  <Card key={idx}>
                    <CardContent className="space-y-3 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <Badge variant="secondary" className="text-[10px]">
                          {post.angle}
                        </Badge>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => copyPost(post.text)}
                        >
                          <Copy className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                      <p className="whitespace-pre-wrap text-base leading-relaxed">
                        {post.text}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {post.char_count}/280 karakter
                      </p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            {/* Sources */}
            {result.sources.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Kaynaklar</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2 text-sm">
                    {result.sources.map((s, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <ExternalLink className="h-3.5 w-3.5 mt-0.5 flex-shrink-0 text-muted-foreground" />
                        <div>
                          <a
                            href={s.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium hover:text-primary hover:underline"
                          >
                            {s.title}
                          </a>
                          <p className="text-xs text-muted-foreground">
                            {s.source}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            {/* Suggested image — #305 PR-5 */}
            {result.suggested_image && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    Önerilen görsel
                  </CardTitle>
                  <CardDescription>
                    Post içeriğinizle uyumlu, kaynak haberin görseli (skor:{" "}
                    {result.suggested_image.score.toFixed(2)})
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <a
                    href={result.suggested_image.original_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block overflow-hidden rounded-lg border bg-muted"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={result.suggested_image.original_url}
                      alt={
                        result.suggested_image.alt_text ||
                        result.suggested_image.vlm_caption ||
                        "Önerilen görsel"
                      }
                      loading="lazy"
                      referrerPolicy="no-referrer"
                      className="max-h-[300px] w-full object-contain"
                    />
                  </a>
                  {result.suggested_image.vlm_caption && (
                    <p className="text-sm text-muted-foreground">
                      {result.suggested_image.vlm_caption}
                    </p>
                  )}
                  {result.suggested_image.depicts &&
                    result.suggested_image.depicts.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {result.suggested_image.depicts.map((d, i) => (
                          <Badge key={i} variant="outline">
                            {d}
                          </Badge>
                        ))}
                      </div>
                    )}
                  <p className="text-xs text-muted-foreground">
                    Görsel kaynak haberin sayfasından gelir. X paylaşımında
                    görseli kullanırken kaynağı belirtmeniz tavsiye edilir
                    (FSEK).
                  </p>
                </CardContent>
              </Card>
            )}

            {/* Warnings */}
            {result.warnings.length > 0 && (
              <Card>
                <CardContent className="py-3 text-xs text-muted-foreground">
                  ⚠️ {result.warnings.join("; ")}
                </CardContent>
              </Card>
            )}

            {/* Cost / lineage */}
            <Card>
              <CardContent className="grid gap-2 py-3 text-xs text-muted-foreground md:grid-cols-2">
                <div>
                  <span className="font-medium">ID:</span>{" "}
                  <span className="font-mono">{result.id.slice(0, 12)}…</span>
                </div>
                <div>
                  <span className="font-medium">Maliyet:</span>{" "}
                  ${(result.cost_usd ?? 0).toFixed(4)}
                </div>
              </CardContent>
            </Card>
          </>
        )}

        {result && result.status === "failed" && (
          <Card className="border-red-200 bg-red-50 dark:bg-red-950/30">
            <CardHeader>
              <CardTitle className="text-red-900 dark:text-red-100">
                Üretim başarısız
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm">
                {result.warnings.join("; ") || "Bilinmeyen hata"}
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Streaming preview (#527) — posts geldikçe progressive olarak render
// ============================================================================

function streamingButtonLabel(stage: string): string {
  switch (stage) {
    case "planning":
      return "Plan hazırlanıyor…";
    case "retrieving":
      return "Kaynaklar getiriliyor…";
    case "generating":
      return "Yazıyor…";
    case "finalizing":
      return "Tamamlanıyor…";
    case "validating":
      return "Doğrulanıyor…";
    default:
      return "Üretiliyor…";
  }
}

function StreamingPreview({
  state,
}: {
  state: ReturnType<typeof useGenerationStream>["state"];
}) {
  const stageLabel = streamingButtonLabel(state.stage);
  return (
    <div className="space-y-3">
      {/* Stage banner */}
      <Card className="border-l-4 border-l-accent-500">
        <CardContent className="flex items-center justify-between py-3 text-sm">
          <div className="flex items-center gap-2">
            <Loader2
              aria-hidden="true"
              className="h-4 w-4 animate-spin text-accent-500"
            />
            <span className="font-medium">{stageLabel}</span>
            {state.topicQuery && (
              <Badge variant="outline" className="text-[10px]">
                {state.topicQuery}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {state.firstByteAt && state.startedAt && (
              <span>
                İlk byte: {Math.max(0, Math.round(state.firstByteAt - state.startedAt))}
                ms
              </span>
            )}
            {state.posts.length > 0 && (
              <span>· {state.posts.length} post hazır</span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* #545 — Summary mode (output_type=summary) live render — eğer
          summaryDocItems veya summaryDocTitle dolduysa, posts yerine onu göster */}
      {(state.summaryDocItems.length > 0 || state.summaryDocTitle) && (
        <Card>
          <CardContent className="space-y-3 py-4">
            {state.summaryDocTitle && (
              <h3 className="text-lg font-semibold leading-tight">
                {state.summaryDocTitle}
              </h3>
            )}
            {state.summaryDocItems.length === 0 && state.stage === "generating" && (
              <div className="animate-pulse space-y-2">
                <div className="h-4 w-full rounded bg-muted" />
                <div className="h-4 w-5/6 rounded bg-muted" />
              </div>
            )}
            <ol className="space-y-3">
              {state.summaryDocItems.map((item, idx) => (
                <li key={idx} className="flex gap-3">
                  <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-primary">
                    {idx + 1}
                  </span>
                  <div className="flex-1 space-y-1">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">
                      {item.event}
                    </p>
                    {(item.source || item.date) && (
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        {item.source && (
                          <Badge variant="outline" className="text-[10px]">
                            {item.source}
                          </Badge>
                        )}
                        {item.date && item.date !== "bilinmiyor" && (
                          <span>{item.date}</span>
                        )}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      {/* Posts (x_post mode) — geldikçe görünür. Summary varsa bu blok skip
          (her ikisi aynı anda dolu olmaz; planner'a göre ya posts ya summary). */}
      {state.summaryDocItems.length === 0 && !state.summaryDocTitle &&
        state.posts.length === 0 && state.stage !== "generating" && (
        <Card>
          <CardContent className="py-8 text-center text-xs text-muted-foreground">
            {stageLabel}
          </CardContent>
        </Card>
      )}

      {state.summaryDocItems.length === 0 && !state.summaryDocTitle &&
        state.posts.length === 0 && state.stage === "generating" && (
        <Card className="animate-pulse">
          <CardContent className="space-y-2 py-4">
            <div className="h-3 w-1/4 rounded bg-muted" />
            <div className="h-4 w-full rounded bg-muted" />
            <div className="h-4 w-5/6 rounded bg-muted" />
            <div className="h-4 w-2/3 rounded bg-muted" />
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {state.summaryDocItems.length === 0 && !state.summaryDocTitle && state.posts.map((p) => (
          <Card key={p.index}>
            <CardContent className="space-y-3 py-4">
              <div className="flex items-start justify-between gap-3">
                <Badge variant="secondary" className="text-[10px]">
                  {p.angle || `Paylaşım ${p.index + 1}`}
                </Badge>
              </div>
              <p className="whitespace-pre-wrap text-base leading-relaxed">
                {p.text}
              </p>
              <p className="text-xs text-muted-foreground">
                {p.char_count}/280 karakter
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
