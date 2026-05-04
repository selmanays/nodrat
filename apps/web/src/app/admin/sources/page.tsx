"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
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
    return <Badge variant="secondary">Pasif</Badge>;
  }
  if (source.robots_txt_compliant === false) {
    return <Badge variant="destructive">Robots engelli</Badge>;
  }
  if (source.robots_txt_compliant === null) {
    return <Badge variant="outline">Kontrol bekliyor</Badge>;
  }
  return <Badge variant="secondary">Aktif</Badge>;
}

const TYPE_LABEL: Record<SourceType, string> = {
  rss: "RSS",
  category_page: "Kategori",
  manual: "Manuel",
};

function typeBadge(type: SourceType) {
  return <Badge variant="outline">{TYPE_LABEL[type]}</Badge>;
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

      <Card className="rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-2">
              <Select
                value={statusFilter}
                onValueChange={(v) => setStatusFilter(v as FilterStatus)}
              >
                <SelectTrigger size="sm" className="w-[160px]">
                  <SelectValue placeholder="Durum" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tüm durumlar</SelectItem>
                  <SelectItem value="active">Aktif</SelectItem>
                  <SelectItem value="inactive">Pasif</SelectItem>
                </SelectContent>
              </Select>
              <Select
                value={typeFilter}
                onValueChange={(v) =>
                  setTypeFilter(v as SourceType | "all")
                }
              >
                <SelectTrigger size="sm" className="w-[160px]">
                  <SelectValue placeholder="Tür" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tüm türler</SelectItem>
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
            >
              <RefreshCw className={cn(loading && "animate-spin")} />
              Yenile
            </Button>
          </div>
        </CardHeader>
        <CardContent className="px-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-b bg-muted/50 hover:bg-muted/50">
                  <TableHead className="px-6">Kaynak</TableHead>
                  <TableHead>Tür</TableHead>
                  <TableHead>Durum</TableHead>
                  <TableHead>Güvenilirlik</TableHead>
                  <TableHead>Aralık</TableHead>
                  <TableHead className="px-6 text-right">İşlem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i}>
                      <TableCell className="px-6">
                        <Skeleton className="h-4 w-40" />
                        <Skeleton className="mt-1.5 h-3 w-32" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-12" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-16" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-4 w-12" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-4 w-16" />
                      </TableCell>
                      <TableCell className="px-6 text-right">
                        <Skeleton className="ml-auto h-8 w-16" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : sources.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={6}
                      className="h-32 text-center text-sm text-muted-foreground"
                    >
                      Filtreye uyan kaynak yok.
                    </TableCell>
                  </TableRow>
                ) : (
                  sources.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell className="px-6">
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
                      <TableCell className="px-6 text-right">
                        <Button asChild size="sm" variant="outline">
                          <Link href={`/admin/sources/${s.id}`}>Detay</Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
