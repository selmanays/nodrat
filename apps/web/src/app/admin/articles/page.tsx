"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ImageIcon, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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

const STATUS_VARIANT: Record<string, "muted" | "warning" | "success" | "error" | "secondary"> = {
  discovered: "muted",
  fetched: "warning",
  cleaned: "success",
  failed: "error",
  archived: "secondary",
};

function statusBadge(status: string) {
  return (
    <Badge variant={STATUS_VARIANT[status] ?? "muted"}>
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
  const [total, setTotal] = useState(0);
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Haberler</h1>
          <p className="text-sm text-muted-foreground">
            {total} kayıt — pipeline durumu aşağıda. Reprocess için detay
            sayfasına geç.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => void load()}
          disabled={loading}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Yenile
        </Button>
      </div>

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
        <div className="rounded-md border bg-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs font-semibold uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-3 min-w-[280px]">Başlık</th>
                <th className="px-4 py-3">Kaynak</th>
                <th className="px-4 py-3">Durum</th>
                <th className="px-4 py-3">Confidence</th>
                <th className="px-4 py-3">Yayın</th>
                <th className="px-4 py-3">Görsel</th>
                <th className="px-4 py-3 text-right">İşlem</th>
              </tr>
            </thead>
            <tbody>
              {articles.map((a) => (
                <tr
                  key={a.id}
                  className="border-t hover:bg-muted/30 transition-colors"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium line-clamp-1">{a.title}</div>
                    <div className="text-xs text-muted-foreground line-clamp-1">
                      {a.author && `${a.author} · `}
                      {a.text_length > 0 ? `${a.text_length} char` : "metin yok"}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {a.source_name ?? "—"}
                  </td>
                  <td className="px-4 py-3">{statusBadge(a.status)}</td>
                  <td className="px-4 py-3 text-xs font-mono">
                    {a.extraction_confidence !== null
                      ? a.extraction_confidence.toFixed(2)
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {formatDate(a.published_at)}
                  </td>
                  <td className="px-4 py-3">
                    {a.has_images && (
                      <ImageIcon className="h-4 w-4 text-muted-foreground" />
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/admin/articles/${a.id}`}>Detay</Link>
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
