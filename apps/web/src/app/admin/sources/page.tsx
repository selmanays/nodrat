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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Kaynaklar</h1>
          <p className="text-sm text-muted-foreground">
            Toplam {sources.length} kaynak. Yeni eklemeden önce 5 maddelik
            uyumluluk kontrolü zorunludur.
          </p>
        </div>
        <Button asChild>
          <Link href="/admin/sources/new">
            <Plus />
            Yeni kaynak
          </Link>
        </Button>
      </div>

      <Card>
        <CardContent className="flex flex-wrap items-end gap-4 pt-6">
          <div className="space-y-1.5">
            <Label className="text-xs">Durum</Label>
            <Select
              value={statusFilter}
              onValueChange={(v) => setStatusFilter(v as FilterStatus)}
            >
              <SelectTrigger className="w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Hepsi</SelectItem>
                <SelectItem value="active">Aktif</SelectItem>
                <SelectItem value="inactive">Pasif</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Tür</Label>
            <Select
              value={typeFilter}
              onValueChange={(v) => setTypeFilter(v as SourceType | "all")}
            >
              <SelectTrigger className="w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Hepsi</SelectItem>
                <SelectItem value="rss">RSS</SelectItem>
                <SelectItem value="category_page">Kategori sayfa</SelectItem>
                <SelectItem value="manual">Manuel</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void load()}
            disabled={loading}
            className="ml-auto"
          >
            <RefreshCw className={loading ? "animate-spin" : ""} />
            Yenile
          </Button>
        </CardContent>
      </Card>

      {loading ? (
        <Card>
          <CardContent className="p-12 text-center text-sm text-muted-foreground">
            Yükleniyor…
          </CardContent>
        </Card>
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
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Kaynak</TableHead>
                <TableHead>Tür</TableHead>
                <TableHead>Durum</TableHead>
                <TableHead>Güvenilirlik</TableHead>
                <TableHead>Aralık</TableHead>
                <TableHead className="text-right">İşlem</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>
                    <div className="font-medium">{s.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {s.domain}
                    </div>
                  </TableCell>
                  <TableCell>{typeBadge(s.type)}</TableCell>
                  <TableCell>{statusBadge(s)}</TableCell>
                  <TableCell className="font-mono tabular-nums">
                    {s.reliability_score.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {s.crawl_interval_minutes} dk
                  </TableCell>
                  <TableCell className="text-right">
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/admin/sources/${s.id}`}>Detay</Link>
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
