"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Bookmark,
  BookmarkCheck,
  Copy,
  ExternalLink,
  Flag,
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
import {
  ApiException,
  flagHalu,
  getMyGeneration,
  saveGeneration,
  unsaveGeneration,
  type GenerateResponse,
} from "@/lib/api";
import { formatTrDateTime } from "@/lib/format";

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  queued: "secondary",
  running: "outline",
  completed: "secondary",
  failed: "destructive",
  insufficient_data: "outline",
};

const STATUS_LABEL: Record<string, string> = {
  queued: "Sırada",
  running: "Üretiliyor",
  completed: "Tamamlandı",
  failed: "Başarısız",
  insufficient_data: "Yetersiz kaynak",
};

export default function GenerationDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const [gen, setGen] = useState<GenerateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getMyGeneration(id)
      .then((g) => {
        setGen(g);
        // Status saved_at için API'de göstermiyoruz — listeden gelen bilgi yok
        // Kullanıcı save butonunu manual yönetir
      })
      .catch((err: ApiException) => {
        toast.error(err.message || "Yüklenemedi");
      })
      .finally(() => setLoading(false));
  }, [id]);

  async function handleSave() {
    if (!gen) return;
    try {
      if (saved) {
        await unsaveGeneration(gen.id);
        setSaved(false);
        toast.success("Kaydedilenler listesinden kaldırıldı");
      } else {
        await saveGeneration(gen.id);
        setSaved(true);
        toast.success("Kaydedildi");
      }
    } catch (err) {
      toast.error((err as ApiException).message || "İşlem başarısız");
    }
  }

  async function handleFlagHalu() {
    if (!gen) return;
    const reason = window.prompt("Halüsinasyon detayı (opsiyonel):");
    try {
      await flagHalu(gen.id, reason || undefined);
      toast.success("Bildirildi — incelenecek");
    } catch (err) {
      toast.error((err as ApiException).message || "Bildirim başarısız");
    }
  }

  function copyPost(text: string) {
    navigator.clipboard.writeText(text).then(
      () => toast.success("Panoya kopyalandı"),
      () => toast.error("Kopyalama başarısız"),
    );
  }

  if (loading) {
    return <div className="text-sm text-muted-foreground">Yükleniyor…</div>;
  }

  if (!gen) {
    return (
      <div className="space-y-4">
        <Button asChild variant="ghost" size="sm">
          <Link href="/app/generations">
            <ArrowLeft className="h-4 w-4" />
            Geçmişe dön
          </Link>
        </Button>
        <p>Üretim bulunamadı.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <Button asChild variant="ghost" size="sm">
          <Link href="/app/generations">
            <ArrowLeft className="h-4 w-4" />
            Geçmişe dön
          </Link>
        </Button>
        <div className="flex items-center gap-2">
          <Badge variant={STATUS_VARIANT[gen.status] ?? "muted"}>
            {STATUS_LABEL[gen.status] ?? gen.status}
          </Badge>
          <Badge variant="outline">{gen.mode}</Badge>
          <Badge variant="outline">{gen.output_type}</Badge>
        </div>
      </div>

      {/* Request */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">İstek</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-base">{gen.request_text}</p>
          <p className="mt-2 text-xs text-muted-foreground">
            {formatTrDateTime(gen.created_at)}
          </p>
        </CardContent>
      </Card>

      {/* Insufficient */}
      {gen.status === "insufficient_data" && (
        <Card className="border-amber-200 bg-amber-50 dark:bg-amber-950/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-amber-900 dark:text-amber-100">
              <AlertTriangle className="h-5 w-5" />
              Yetersiz kaynak
            </CardTitle>
            <CardDescription className="text-amber-800 dark:text-amber-200">
              Halüsinasyon riskine karşı kaynak yetersizse içerik üretilmedi.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {gen.suggestions.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-amber-700">•</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Posts */}
      {gen.status === "completed" && (
        <>
          <div className="flex items-center justify-end gap-2">
            <Button variant="outline" size="sm" onClick={handleSave}>
              {saved ? (
                <BookmarkCheck className="h-3.5 w-3.5" />
              ) : (
                <Bookmark className="h-3.5 w-3.5" />
              )}
              {saved ? "Kayıtlı" : "Kaydet"}
            </Button>
            <Button variant="ghost" size="sm" onClick={handleFlagHalu}>
              <Flag className="h-3.5 w-3.5" />
              Halüsinasyon bildir
            </Button>
          </div>

          <div className="space-y-3">
            {gen.posts.map((post, idx) => (
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

          {gen.sources.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Kaynaklar</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  {gen.sources.map((s, i) => (
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
                        <p className="text-xs text-muted-foreground">{s.source}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {gen.warnings.length > 0 && (
        <Card>
          <CardContent className="py-3 text-xs text-muted-foreground">
            ⚠️ {gen.warnings.join("; ")}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
