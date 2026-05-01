"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";

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
  listSources,
  type SourcePublic,
  type SourceType,
} from "@/lib/api";
import { toast } from "sonner";

type FilterStatus = "all" | "active" | "inactive";

function statusBadge(source: SourcePublic) {
  if (!source.is_active) {
    return <Badge variant="muted">Pasif</Badge>;
  }
  if (source.robots_txt_compliant === false) {
    return <Badge variant="error">Robots engelli</Badge>;
  }
  if (source.robots_txt_compliant === null) {
    return <Badge variant="warning">Kontrol bekliyor</Badge>;
  }
  return <Badge variant="success">Aktif</Badge>;
}

function typeBadge(type: SourceType) {
  const map: Record<SourceType, string> = {
    rss: "RSS",
    category_page: "Kategori",
    manual: "Manuel",
  };
  return <Badge variant="outline">{map[type]}</Badge>;
}

export default function AdminSourcesPage() {
  const [sources, setSources] = useState<SourcePublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<FilterStatus>("all");
  const [typeFilter, setTypeFilter] = useState<SourceType | "all">("all");

  async function load() {
    setLoading(true);
    try {
      const data = await listSources({
        is_active:
          statusFilter === "all" ? undefined : statusFilter === "active",
        type: typeFilter === "all" ? undefined : typeFilter,
        limit: 100,
      });
      setSources(data);
    } catch (error) {
      const apiError = error as ApiException;
      toast.error(apiError.message || "Kaynaklar yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, typeFilter]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Kaynaklar</h1>
          <p className="text-sm text-muted-foreground">
            Toplam {sources.length} kaynak. Yeni eklemeden önce 5 maddelik
            uyumluluk kontrolü zorunludur.
          </p>
        </div>
        <Button asChild>
          <Link href="/admin/sources/new">
            <Plus className="h-4 w-4" />
            Yeni kaynak
          </Link>
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="flex flex-wrap items-end gap-4 py-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Durum
            </label>
            <select
              value={statusFilter}
              onChange={(e) =>
                setStatusFilter(e.target.value as FilterStatus)
              }
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="all">Hepsi</option>
              <option value="active">Aktif</option>
              <option value="inactive">Pasif</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Tür
            </label>
            <select
              value={typeFilter}
              onChange={(e) =>
                setTypeFilter(e.target.value as SourceType | "all")
              }
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="all">Hepsi</option>
              <option value="rss">RSS</option>
              <option value="category_page">Kategori sayfa</option>
              <option value="manual">Manuel</option>
            </select>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void load()}
            disabled={loading}
            className="ml-auto"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Yenile
          </Button>
        </CardContent>
      </Card>

      {/* Liste */}
      {loading ? (
        <div className="rounded-md border bg-card p-12 text-center text-sm text-muted-foreground">
          Yükleniyor…
        </div>
      ) : sources.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Henüz kaynak yok</CardTitle>
            <CardDescription>
              İlk RSS kaynağını eklemek için yukarıdaki butonu kullan.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="rounded-md border bg-card">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs font-semibold uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Kaynak</th>
                <th className="px-4 py-3">Tür</th>
                <th className="px-4 py-3">Durum</th>
                <th className="px-4 py-3">Güvenilirlik</th>
                <th className="px-4 py-3">Aralık</th>
                <th className="px-4 py-3 text-right">İşlem</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr
                  key={s.id}
                  className="border-t hover:bg-muted/30 transition-colors"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium">{s.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {s.domain}
                    </div>
                  </td>
                  <td className="px-4 py-3">{typeBadge(s.type)}</td>
                  <td className="px-4 py-3">{statusBadge(s)}</td>
                  <td className="px-4 py-3">
                    <span className="font-mono">{s.reliability_score.toFixed(2)}</span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {s.crawl_interval_minutes} dk
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/admin/sources/${s.id}`}>Detay</Link>
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
