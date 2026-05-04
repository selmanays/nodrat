"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Archive,
  CircleCheck,
  CircleX,
  ExternalLink,
  ImageIcon,
  Loader,
  MoreVertical,
  RefreshCw,
  Search,
} from "lucide-react";
import { toast } from "sonner";
import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
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
import { PageHeader } from "@/components/blocks/page-header";
import { cn } from "@/lib/utils";
import {
  ApiException,
  articleStats,
  listArticles,
  listSources,
  type ArticleStatsResponse,
  type ArticleSummary,
  type SourcePublic,
} from "@/lib/api";

const PAGE_SIZE = 20;

const STATUS_LABEL: Record<string, string> = {
  discovered: "Keşfedildi",
  fetched: "İndirildi",
  cleaned: "Temizlendi",
  failed: "Başarısız",
  archived: "Arşiv",
};

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  discovered: "secondary",
  fetched: "secondary",
  cleaned: "secondary",
  failed: "destructive",
  archived: "outline",
};

const STATUS_ICON: Record<string, LucideIcon> = {
  discovered: Loader,
  fetched: Loader,
  cleaned: CircleCheck,
  failed: CircleX,
  archived: Archive,
};

const STATUS_ICON_CLASS: Record<string, string> = {
  cleaned: "text-emerald-500",
  failed: "text-destructive",
  discovered: "text-muted-foreground",
  fetched: "text-muted-foreground",
  archived: "text-muted-foreground",
};

function StatusBadge({ status }: { status: string }) {
  const Icon = STATUS_ICON[status] ?? Loader;
  const label = STATUS_LABEL[status] ?? status;
  const variant = STATUS_VARIANT[status] ?? "secondary";
  return (
    <Badge variant={variant} className="gap-1">
      <Icon className={cn(STATUS_ICON_CLASS[status])} />
      {label}
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
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page, setPage] = useState(1);

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchInput), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Filter değişince sayfa 1'e dön
  useEffect(() => {
    setPage(1);
  }, [statusFilter, sourceFilter, debouncedSearch]);

  async function load() {
    setLoading(true);
    try {
      const [list, statsResp] = await Promise.all([
        listArticles({
          status: statusFilter === "all" ? undefined : statusFilter,
          source_id: sourceFilter === "all" ? undefined : sourceFilter,
          q: debouncedSearch || undefined,
          limit: PAGE_SIZE,
          offset: (page - 1) * PAGE_SIZE,
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
      /* sessiz fail */
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, sourceFilter, debouncedSearch, page]);

  useEffect(() => {
    void loadSources();
  }, []);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const pageEnd = Math.min(total, page * PAGE_SIZE);

  const pageNumbers = useMemo(() => {
    // Compact: ilk, son, current ± 1, gerektiğinde …
    const range: (number | "...")[] = [];
    const add = (n: number) => {
      if (!range.includes(n)) range.push(n);
    };
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) add(i);
    } else {
      add(1);
      if (page > 3) range.push("...");
      for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) {
        add(i);
      }
      if (page < totalPages - 2) range.push("...");
      add(totalPages);
    }
    return range;
  }, [page, totalPages]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Haberler"
        description="RSS ve DOM kaynaklarından çekilen haberlerin pipeline durumunu izle, gerektiğinde yeniden işle."
      />

      {/* Stats summary */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        {loading && !stats
          ? Array.from({ length: 5 }).map((_, i) => (
              <Card
                key={i}
                className="rounded-2xl shadow-none ring-[var(--border)]"
              >
                <CardContent className="p-4">
                  <Skeleton className="h-7 w-12" />
                  <Skeleton className="mt-2 h-3 w-20" />
                </CardContent>
              </Card>
            ))
          : (stats?.by_status ?? []).map((s) => (
              <Card
                key={s.status}
                className="rounded-2xl shadow-none ring-[var(--border)]"
              >
                <CardContent className="p-4">
                  <div className="text-2xl font-semibold tabular-nums">
                    {s.count.toLocaleString("tr-TR")}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {STATUS_LABEL[s.status] ?? s.status}
                  </div>
                </CardContent>
              </Card>
            ))}
      </div>

      {/* Filtreler ve yenile butonu — kart dışında */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger size="sm" className="w-[160px]">
              <SelectValue placeholder="Durum" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tüm durumlar</SelectItem>
              {Object.entries(STATUS_LABEL).map(([k, v]) => (
                <SelectItem key={k} value={k}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={sourceFilter} onValueChange={setSourceFilter}>
            <SelectTrigger size="sm" className="w-[200px]">
              <SelectValue placeholder="Kaynak" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tüm kaynaklar</SelectItem>
              {sources.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Başlık ara…"
              className="h-8 w-[240px] pl-8 text-sm"
            />
          </div>
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

      {/* Tablo card'ı */}
      <Card className="overflow-hidden rounded-2xl py-0 shadow-none ring-[var(--border)]">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-b bg-muted/50 hover:bg-muted/50">
                  <TableHead className="px-6">Başlık</TableHead>
                  <TableHead>Kaynak</TableHead>
                  <TableHead>Durum</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Yayın</TableHead>
                  <TableHead>Görsel</TableHead>
                  <TableHead className="px-6 text-right">İşlem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 8 }).map((_, i) => (
                    <TableRow key={i}>
                      <TableCell className="px-6">
                        <Skeleton className="h-4 w-64" />
                        <Skeleton className="mt-1.5 h-3 w-32" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-3 w-24" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-24" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-3 w-10" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-3 w-20" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="size-4 rounded" />
                      </TableCell>
                      <TableCell className="px-6 text-right">
                        <Skeleton className="ml-auto size-8 rounded-full" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : articles.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="h-32 text-center text-sm text-muted-foreground"
                    >
                      Filtreye uyan haber yok.
                    </TableCell>
                  </TableRow>
                ) : (
                  articles.map((a) => (
                    <TableRow key={a.id}>
                      <TableCell className="max-w-[420px] px-6">
                        <div className="line-clamp-1 font-medium">
                          {a.title}
                        </div>
                        <div className="line-clamp-1 text-xs text-muted-foreground">
                          {a.author && `${a.author} · `}
                          {a.text_length > 0
                            ? `${a.text_length} karakter`
                            : "metin yok"}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs">
                        {a.source_name ?? "—"}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={a.status} />
                      </TableCell>
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
                          <ImageIcon className="size-4 text-muted-foreground" />
                        )}
                      </TableCell>
                      <TableCell className="px-6 text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger
                            aria-label={`${a.title} işlemleri`}
                            className="ml-auto inline-flex size-8 items-center justify-center rounded-full text-muted-foreground transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 data-[state=open]:bg-muted data-[state=open]:text-foreground [&_svg]:size-4 [&_svg]:shrink-0"
                          >
                            <MoreVertical />
                            <span className="sr-only">İşlemler</span>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem asChild>
                              <Link href={`/admin/articles/${a.id}`}>
                                <ExternalLink />
                                Detayı aç
                              </Link>
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          {/* Footer: result count + pagination */}
          <div className="flex flex-col items-start gap-3 border-t px-6 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
            <span className="text-muted-foreground">
              {loading ? (
                <Skeleton className="inline-block h-3.5 w-32 align-middle" />
              ) : total === 0 ? (
                "0 haber"
              ) : (
                <>
                  <span className="font-medium tabular-nums text-foreground">
                    {pageStart}–{pageEnd}
                  </span>{" "}
                  / {total.toLocaleString("tr-TR")} haber
                </>
              )}
            </span>
            {totalPages > 1 && (
              <Pagination className="mx-0 w-auto justify-end">
                <PaginationContent>
                  <PaginationItem>
                    <PaginationPrevious
                      href="#"
                      onClick={(e) => {
                        e.preventDefault();
                        if (page > 1) setPage(page - 1);
                      }}
                      aria-disabled={page <= 1}
                      className={cn(
                        page <= 1 && "pointer-events-none opacity-50",
                      )}
                    />
                  </PaginationItem>
                  {pageNumbers.map((n, idx) =>
                    n === "..." ? (
                      <PaginationItem key={`gap-${idx}`}>
                        <span className="px-2 text-muted-foreground">…</span>
                      </PaginationItem>
                    ) : (
                      <PaginationItem key={n}>
                        <PaginationLink
                          href="#"
                          isActive={n === page}
                          onClick={(e) => {
                            e.preventDefault();
                            setPage(n);
                          }}
                        >
                          {n}
                        </PaginationLink>
                      </PaginationItem>
                    ),
                  )}
                  <PaginationItem>
                    <PaginationNext
                      href="#"
                      onClick={(e) => {
                        e.preventDefault();
                        if (page < totalPages) setPage(page + 1);
                      }}
                      aria-disabled={page >= totalPages}
                      className={cn(
                        page >= totalPages && "pointer-events-none opacity-50",
                      )}
                    />
                  </PaginationItem>
                </PaginationContent>
              </Pagination>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
