"use client";

/**
 * /app/clusters/[id] — Küme detay (Faz 4).
 *
 * Kümenin (kullanıcıya ait) geçmiş üretimleri = artefaktlar. Her artefakt
 * yayınlanabilir bir içerik kartı; tıkla → canvas (revizyon geçmişi + düzenle +
 * quick-action). Sohbet geçmişi DEĞİL — küme başlığı altında üretim listesi.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { ArrowLeft, FileText, Layers } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type ApiException } from "@/lib/api";
import { type ArtifactListItem, getClusterArtifacts } from "@/lib/api/clusters";

const ARTIFACT_TYPE_LABEL: Record<string, string> = {
  post: "Gönderi",
  thread: "Thread",
  canvas: "Canvas",
};

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("tr-TR", {
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

export default function ClusterDetailPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const clusterId = params.id;
  const clusterName = search.get("name");

  const [items, setItems] = useState<ArtifactListItem[] | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await getClusterArtifacts(clusterId);
        if (active) setItems(res.artifacts);
      } catch (e) {
        if (active) {
          toast.error((e as ApiException).message || "İçerikler yüklenemedi");
          setItems([]);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [clusterId]);

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
      <div className="space-y-2">
        <Link
          href="/app/clusters"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Kümelerim
        </Link>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Layers className="h-6 w-6 text-primary" />
          {clusterName || "Küme"}
        </h1>
        <p className="text-sm text-muted-foreground">
          Bu konuda ürettiğin içerikler. Bir karta tıkla → düzenle, kısalt, yeniden
          yaz veya thread'e çevir.
        </p>
      </div>

      {items === null ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="space-y-3 py-12 text-center text-sm text-muted-foreground">
            <p>Bu kümede henüz içerik üretmedin.</p>
            <p>
              <Link href="/app/research" className="font-medium text-primary underline">
                Araştırma yap
              </Link>{" "}
              — bu konuda bir soru sorduğunda üretilen cevap buraya bir içerik kartı
              olarak eklenir.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {items.map((a) => (
            <Link key={a.artifact_id} href={`/app/artifacts/${a.artifact_id}`}>
              <Card className="transition-colors hover:border-primary/40">
                <CardContent className="space-y-2 py-4">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <Badge variant="secondary" className="shrink-0">
                      {ARTIFACT_TYPE_LABEL[a.artifact_type] ?? a.artifact_type}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {a.revision_count} sürüm · {fmtDate(a.created_at)}
                    </span>
                  </div>
                  {a.head_preview ? (
                    <p className="line-clamp-2 text-sm text-foreground/90">{a.head_preview}</p>
                  ) : (
                    <p className="text-sm italic text-muted-foreground">(boş içerik)</p>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
