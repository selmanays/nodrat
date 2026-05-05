"use client";

import { FormEvent, useRef, useState } from "react";
import {
  AlertTriangle,
  Bookmark,
  Bot,
  Calendar,
  Copy,
  ExternalLink,
  Flag,
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
import { Textarea } from "@/components/ui/textarea";
import {
  ApiException,
  flagHalu,
  generate,
  saveGeneration,
  type GenerateMode,
  type GenerateRequest,
  type GenerateResponse,
} from "@/lib/api";
import { formatTrDate } from "@/lib/format";

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
  const [maxPosts, setMaxPosts] = useState(3);
  const [tone, setTone] = useState<string>("");
  const [mode, setMode] = useState<GenerateMode | "">("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const requestRef = useRef<HTMLTextAreaElement | null>(null);

  async function runGenerate(payload: GenerateRequest) {
    setSubmitting(true);
    setResult(null);
    try {
      const response = await generate(payload);
      setResult(response);
      if (response.status === "completed") {
        if (response.summary_doc_items && response.summary_doc_items.length > 0) {
          toast.success(`${response.summary_doc_items.length} maddelik özet üretildi`);
        } else {
          toast.success(`${response.posts.length} paylaşım üretildi`);
        }
      } else if (response.status === "insufficient_data") {
        toast.warning("Yeterli kaynak yok — alternatif öneriler aşağıda");
      }
    } catch (error) {
      const apiError = error as ApiException;
      if (apiError.status === 429) {
        toast.error(
          `Kotanız doldu. ${apiError.detail || "24 saat sonra tekrar deneyin."}`,
        );
      } else {
        toast.error(apiError.message || "Üretim başarısız");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!requestText.trim() || requestText.trim().length < 5) {
      toast.error("İstek en az 5 karakter olmalı");
      return;
    }

    await runGenerate({
      request_text: requestText.trim(),
      max_posts: maxPosts,
      tone: tone || undefined,
      mode_hint: mode || undefined,
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
      max_posts: maxPosts,
      tone: tone || undefined,
      mode_hint: newMode,
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
                <select
                  id="max_posts"
                  value={maxPosts}
                  onChange={(e) => setMaxPosts(parseInt(e.target.value))}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value={1}>1</option>
                  <option value={3}>3</option>
                  <option value={5}>5</option>
                  <option value={7}>7</option>
                  <option value={10}>10</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="tone">Ton (opsiyonel)</Label>
                <select
                  id="tone"
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="">Otomatik</option>
                  <option value="tarafsız">Tarafsız</option>
                  <option value="eleştirel">Eleştirel</option>
                  <option value="mizahi">Mizahi</option>
                  <option value="kurumsal">Kurumsal</option>
                  <option value="analitik">Analitik</option>
                  <option value="sade">Sade</option>
                </select>
              </div>
            </div>

            <Button type="submit" className="w-full" disabled={submitting} variant="default">
              <Sparkles className="h-4 w-4" />
              {submitting ? "Üretiliyor… (~20-60 sn)" : "Üret"}
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
        {!result && (
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
