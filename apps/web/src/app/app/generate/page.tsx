"use client";

import { FormEvent, useState } from "react";
import {
  AlertTriangle,
  Bookmark,
  Copy,
  ExternalLink,
  Flag,
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
  type GenerateResponse,
} from "@/lib/api";

// Research-driven örnek prompt'lar (validation/research-findings.md)
const SAMPLE_PROMPTS = [
  "Bu hafta yapay zeka regülasyonlarıyla ilgili 3 X paylaşımı üret",
  "Türkiye ekonomisinde son gelişmeler — analitik tonla",
  "Süper Lig'in son haftası, eleştirel ton",
  "Geçen ay vs bu ay sağlık politikaları kıyas",
  "Bugünkü deprem haberleri, kurumsal ton",
];

export default function GeneratePage() {
  const [requestText, setRequestText] = useState("");
  const [maxPosts, setMaxPosts] = useState(3);
  const [tone, setTone] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<GenerateResponse | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!requestText.trim() || requestText.trim().length < 5) {
      toast.error("İstek en az 5 karakter olmalı");
      return;
    }

    setSubmitting(true);
    setResult(null);
    try {
      const response = await generate({
        request_text: requestText.trim(),
        max_posts: maxPosts,
        tone: tone || undefined,
      });
      setResult(response);
      if (response.status === "completed") {
        toast.success(`${response.posts.length} paylaşım üretildi`);
      } else if (response.status === "insufficient_data") {
        toast.warning("Yeterli kaynak yok — alternatif öneriler aşağıda");
      }
    } catch (error) {
      const apiError = error as ApiException;
      if (apiError.status === 429) {
        toast.error(`Kotanız doldu. ${apiError.detail || "24 saat sonra tekrar deneyin."}`);
      } else {
        toast.error(apiError.message || "Üretim başarısız");
      }
    } finally {
      setSubmitting(false);
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

            <Button type="submit" className="w-full" disabled={submitting} variant="accent">
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
                Nodrat halüsinasyon riskine karşı kaynak yetersizse içerik üretmez.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-sm font-medium">Önerilerimiz:</p>
              <ul className="space-y-2 text-sm">
                {result.suggestions.map((s, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-amber-700">•</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
              {result.warnings.length > 0 && (
                <p className="mt-3 text-xs text-muted-foreground">
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
                <Badge variant="success">Tamamlandı</Badge>
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

            {/* Posts */}
            <div className="space-y-3">
              {result.posts.map((post, idx) => (
                <Card key={idx}>
                  <CardContent className="space-y-3 py-4">
                    <div className="flex items-start justify-between gap-3">
                      <Badge variant="muted" className="text-[10px]">
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
                            className="font-medium hover:text-brand-700 hover:underline"
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
