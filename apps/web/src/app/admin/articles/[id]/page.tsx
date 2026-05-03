"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, RefreshCw, AlertTriangle } from "lucide-react";
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
  getArticle,
  reprocessArticle,
  type ArticleDetail,
} from "@/lib/api";
import { formatTrDateTime } from "@/lib/format";

const STATUS_VARIANT: Record<
  string,
  "muted" | "warning" | "success" | "error" | "secondary"
> = {
  discovered: "muted",
  fetched: "warning",
  cleaned: "success",
  failed: "error",
  archived: "secondary",
};

const STATUS_LABEL: Record<string, string> = {
  discovered: "Keşfedildi",
  fetched: "İndirildi",
  cleaned: "Temizlendi",
  failed: "Başarısız",
  archived: "Arşiv",
};

export default function ArticleDetailPage() {
  const params = useParams<{ id: string }>();
  const articleId = params?.id ?? "";

  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [reprocessing, setReprocessing] = useState(false);

  async function load() {
    if (!articleId) return;
    setLoading(true);
    try {
      const data = await getArticle(articleId);
      setArticle(data);
    } catch (error) {
      const apiError = error as ApiException;
      toast.error(apiError.message || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [articleId]);

  async function handleReprocess() {
    if (!article) return;
    if (article.status === "archived") {
      toast.error("Arşivlenmiş haber yeniden işlenemez");
      return;
    }
    if (!confirm("Bu haberi yeniden indirip temizlemek istediğinden emin misin?"))
      return;

    setReprocessing(true);
    try {
      const result = await reprocessArticle(articleId);
      toast.success(
        `Reprocess başlatıldı (${result.dispatched_task ?? "—"})`,
      );
      await load();
    } catch (error) {
      const apiError = error as ApiException;
      if (apiError.code === "ARCHIVED_NOT_REPROCESSABLE") {
        toast.error("Arşivlenmiş haber yeniden işlenemez");
      } else {
        toast.error(apiError.message || "Reprocess başarısız");
      }
    } finally {
      setReprocessing(false);
    }
  }

  if (loading) {
    return <div className="text-sm text-muted-foreground">Yükleniyor…</div>;
  }

  if (!article) {
    return (
      <div className="space-y-4">
        <Button asChild variant="ghost" size="sm">
          <Link href="/admin/articles">
            <ArrowLeft className="h-4 w-4" />
            Haberlere dön
          </Link>
        </Button>
        <p>Haber bulunamadı.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <Button asChild variant="ghost" size="sm">
          <Link href="/admin/articles">
            <ArrowLeft className="h-4 w-4" />
            Haberlere dön
          </Link>
        </Button>
        <div className="flex items-center gap-2">
          <Badge variant={STATUS_VARIANT[article.status] ?? "muted"}>
            {STATUS_LABEL[article.status] ?? article.status}
          </Badge>
          {article.extraction_confidence !== null && (
            <Badge variant="outline" className="font-mono">
              conf: {article.extraction_confidence.toFixed(2)}
            </Badge>
          )}
        </div>
      </div>

      {/* Title block */}
      <div>
        <h1 className="text-3xl font-semibold tracking-tight leading-tight">
          {article.title}
        </h1>
        {article.subtitle && (
          <p className="mt-2 text-lg text-muted-foreground">
            {article.subtitle}
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
          {article.source_name && (
            <Link
              href={`/admin/sources/${article.source_id}`}
              className="font-medium hover:text-foreground"
            >
              {article.source_name}
            </Link>
          )}
          {article.author && <span>• {article.author}</span>}
          {article.published_at && (
            <span>
              • {formatTrDateTime(article.published_at)}
            </span>
          )}
        </div>
        <a
          href={article.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-xs font-mono text-primary hover:underline underline-offset-4"
        >
          <ExternalLink className="h-3 w-3" />
          {article.source_url}
        </a>
      </div>

      <div className="flex justify-end">
        <Button
          onClick={handleReprocess}
          disabled={reprocessing || article.status === "archived"}
          variant="outline"
        >
          <RefreshCw
            className={`h-4 w-4 ${reprocessing ? "animate-spin" : ""}`}
          />
          {reprocessing ? "Yeniden işleniyor…" : "Yeniden işle"}
        </Button>
      </div>

      {/* Failure warning */}
      {article.status === "failed" && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="flex items-start gap-3 py-4">
            <AlertTriangle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-red-900">
              <p className="font-medium">Bu haberin işlenmesi başarısız oldu.</p>
              <p className="text-xs mt-1">
                Hata detayları failed_jobs tablosunda — Kuyruk &gt; DLQ
                üzerinden incele veya yukarıdan yeniden işle.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Clean text */}
      {article.clean_text && (
        <Card>
          <CardHeader>
            <CardTitle>Temizlenmiş metin</CardTitle>
            <CardDescription>
              {article.clean_text.length} karakter · Dil:{" "}
              <span className="font-mono">{article.language}</span> · PII
              redaction otomatik uygulandı
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="prose prose-sm max-w-none whitespace-pre-wrap rounded-md bg-muted/30 p-4">
              {article.clean_text}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Images */}
      {article.images.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Görseller ({article.images.length})</CardTitle>
            <CardDescription>
              Storage: MinIO bucket / s3://nodrat-images
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {article.images.map((img) => (
                <div
                  key={img.id}
                  className="space-y-2 rounded-md border p-3 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <Badge
                      variant={
                        img.status === "downloaded"
                          ? "success"
                          : img.status === "pending"
                            ? "warning"
                            : img.status === "duplicate"
                              ? "secondary"
                              : "error"
                      }
                    >
                      {img.status}
                    </Badge>
                    {img.discovered_from && (
                      <Badge variant="outline" className="text-[10px]">
                        {img.discovered_from}
                      </Badge>
                    )}
                  </div>
                  {img.mime_type && (
                    <div className="font-mono">
                      {img.mime_type}
                      {img.file_size && ` · ${Math.round(img.file_size / 1024)}KB`}
                    </div>
                  )}
                  <a
                    href={img.original_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block truncate text-primary hover:underline underline-offset-4"
                  >
                    {img.original_url}
                  </a>
                  {img.storage_url && (
                    <div className="font-mono text-[10px] text-muted-foreground truncate">
                      {img.storage_url}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Metadata */}
      <Card>
        <CardHeader>
          <CardTitle>Metadata</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 md:grid-cols-2 text-xs font-mono">
          <div>
            <span className="text-muted-foreground">id:</span> {article.id}
          </div>
          <div>
            <span className="text-muted-foreground">content_hash:</span>{" "}
            {article.content_hash.slice(0, 16)}…
          </div>
          <div>
            <span className="text-muted-foreground">canonical:</span>{" "}
            <span className="break-all">{article.canonical_url}</span>
          </div>
          <div>
            <span className="text-muted-foreground">title_hash:</span>{" "}
            {article.title_hash.slice(0, 16)}…
          </div>
          <div>
            <span className="text-muted-foreground">fetched_at:</span>{" "}
            {formatTrDateTime(article.fetched_at)}
          </div>
          <div>
            <span className="text-muted-foreground">updated_at:</span>{" "}
            {formatTrDateTime(article.updated_at)}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
