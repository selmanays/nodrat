"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Bookmark, Flag } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiException,
  listMyGenerations,
  type GenerationSummary,
} from "@/lib/api";
import { formatTrDate } from "@/lib/format";

const STATUS_LABEL: Record<string, string> = {
  queued: "Sırada",
  running: "Üretiliyor",
  completed: "Tamamlandı",
  failed: "Başarısız",
  insufficient_data: "Yetersiz kaynak",
};

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

interface Props {
  savedOnly?: boolean;
  emptyTitle?: string;
}

export function GenerationList({ savedOnly = false, emptyTitle = "Henüz üretim yok" }: Props) {
  const [items, setItems] = useState<GenerationSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    listMyGenerations({ saved_only: savedOnly, limit: 50 })
      .then((response) => {
        setItems(response.data);
        setTotal(response.total);
      })
      .catch((err: ApiException) => {
        toast.error(err.message || "Yüklenemedi");
      })
      .finally(() => setLoading(false));
  }, [savedOnly]);

  if (loading) {
    return (
      <div className="rounded-md border bg-card p-12 text-center text-sm text-muted-foreground">
        Yükleniyor…
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{emptyTitle}</CardTitle>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link href="/app/generate">Yeni üretim başlat</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{total} üretim</p>
      {items.map((g) => (
        <Card key={g.id} className="hover:shadow-sm transition-shadow">
          <CardContent className="space-y-2 py-4">
            <div className="flex items-start justify-between gap-3">
              <Link
                href={`/app/generations/${g.id}`}
                className="flex-1 font-medium hover:text-brand-700 line-clamp-2"
              >
                {g.request_text}
              </Link>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {g.saved && (
                  <Bookmark className="h-3.5 w-3.5 text-accent-500 fill-current" />
                )}
                {g.halu_flagged && (
                  <Flag className="h-3.5 w-3.5 text-red-500" />
                )}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant={STATUS_VARIANT[g.status] ?? "muted"}>
                {STATUS_LABEL[g.status] ?? g.status}
              </Badge>
              <Badge variant="outline">{g.mode}</Badge>
              <Badge variant="outline">{g.output_type}</Badge>
              {g.posts_count > 0 && (
                <span className="text-muted-foreground">
                  {g.posts_count} paylaşım
                </span>
              )}
              <span className="ml-auto text-muted-foreground">
                {formatTrDate(g.created_at)}
              </span>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
