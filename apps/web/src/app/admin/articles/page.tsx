"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ImageIcon, Search } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/blocks/page-header";
import {
  ApiException,
  articleStats,
  listArticles,
  listSources,
  type ArticleStatsResponse,
  type ArticleSummary,
  type SourcePublic,
} from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  discovered: "Keşfedildi",
  fetched: "İndirildi",
  cleaned: "Temizlendi",
  failed: "Başarısız",
  archived: "Arşiv",
};

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  discovered: "secondary",
  fetched: "outline",
  cleaned: "secondary",
  failed: "destructive",
  archived: "secondary",
};

function statusBadge(status: string) {
  return (
    <Badge variant={STATUS_VARIANT[status] ?? "secondary"}>
      {STATUS_LABEL[status] ?? status}
    </Badge>
  );
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("tr-TR", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function AdminArticlesPage() {
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [stats, setStats] = useState<ArticleStatsResponse | null>(null);
  const [sources, setSources] = useState<SourcePublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [_total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");

  async function load() {
    setLoading(true);
    try {
      const [list, statsResp] = await Promise.all([
        listArticles({
          status: statusFilter || undefined,
          source_id: sourceFilter || undefined,
          q: search || undefined,
          limit: 50,
        }),
        articleStats(),
      ]);
      setArticles(list.data);
      setTotal(list.total);
      setStats(statsResp);
    } catch (error) {
      const apiError = error as ApiException;
      toast.error(apiError.message || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  async function loadSources() {
    try {
      const data = await listSources({ limit: 200 });
      setSources(data);
    } catch {
      // Sessiz fail — filter dropdown boş kalır
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, sourceFilter, search]);

  useEffect(() => {
    void loadSources();
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Haberler"
        description="RSS ve DOM kaynaklarından çekilen haberlerin pipeline durumunu izle, gerektiğinde yeniden işle."
      />

      {/* Stats summary */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          {stats.by_status.map((s) => (
            <Card key={s.status}>
              <CardContent className="p-4">
                <div className="text-2xl font-semibold">{s.count}</div>
                <div className="text-xs text-muted-foreground">
                  {STATUS_LABEL[s.status] ?? s.status}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="flex flex-wrap items-end gap-4 py-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Durum
            </label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Hepsi</option>
              {Object.entries(STATUS_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Kaynak
            </label>
            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[180px]"
            >
              <option value="">Hepsi</option>
              {sources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1 min-w-[240px] space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Başlık ara
            </label>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setSearch(searchInput);
              }}
              className="flex gap-2"
            >
              <Input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Anahtar kelime…"
                className="h-9"
              />
              <Button type="submit" size="sm" variant="outline">
                <Search className="h-3.5 w-3.5" />
              </Button>
              {search && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setSearch("");
                    setSearchInput("");
                  }}
                >
                  Temizle
                </Button>
              )}
            </form>
          </div>
        </CardContent>
      </Card>

      {/* Liste */}
      {loading ? (
        <div className="rounded-md border bg-card p-12 text-center text-sm text-muted-foreground">
          Yükleniyor…
        </div>
      ) : articles.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Henüz haber yok</CardTitle>
          </CardHeader>
        </Card>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="min-w-[280px]">Başlık</TableHead>
                <TableHead>Kaynak</TableHead>
                <TableHead>Durum</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Yayın</TableHead>
                <TableHead>Görsel</TableHead>
                <TableHead className="text-right">İşlem</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {articles.map((a) => (
                <TableRow key={a.id}>
                  <TableCell>
                    <div className="line-clamp-1 font-medium">{a.title}</div>
                    <div className="line-clamp-1 text-xs text-muted-foreground">
                      {a.author && `${a.author} · `}
                      {a.text_length > 0
                        ? `${a.text_length} char`
                        : "metin yok"}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs">
                    {a.source_name ?? "—"}
                  </TableCell>
                  <TableCell>{statusBadge(a.status)}</TableCell>
                  <TableCell className="font-mono text-xs tabular-nums">
                    {a.extraction_confidence !== null
                      ? a.extraction_confidence.toFixed(2)
                      : "—"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDate(a.published_at)}
                  </TableCell>
                  <TableCell>
                    {a.has_images && (
                      <ImageIcon className="h-4 w-4 text-muted-foreground" />
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/admin/articles/${a.id}`}>Detay</Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
