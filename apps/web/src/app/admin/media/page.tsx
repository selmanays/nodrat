"use client";

/**
 * Admin Media — NIM VLM ile işlenmiş haber görselleri (#304 MVP-1.4 PR-4).
 *
 * Process & discard mimarisi: original_url + alt_text + caption + vlm_caption
 * + ocr_text + depicts saklanır; bytes saklanmaz.
 *
 * docs/engineering/data-model.md §3.5 (article_images)
 * docs/engineering/architecture.md §3.1 (image_vlm_queue)
 */

import { useEffect, useState } from "react";
import {
  CalendarIcon,
  ImageOff,
  MoreVertical,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { format } from "date-fns";
import { tr as trDate } from "date-fns/locale";
import { tr } from "react-day-picker/locale";
import type { DateRange } from "react-day-picker";
import { toast } from "sonner";

import { PageHeader } from "@/components/blocks/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
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
import { formatTrDateTime } from "@/lib/format";
import {
  ApiException,
  adminMediaStats,
  listAdminMedia,
  listSources,
  reprocessMedia,
  type MediaImage,
  type MediaListFilters,
  type MediaStatsResponse,
  type MediaStatus,
  type SourcePublic,
} from "@/lib/api";

// ============================================================================
// Sözlükler
// ============================================================================

const STATUS_LABEL: Record<MediaStatus, string> = {
  pending: "Bekliyor",
  processed: "İşlendi",
  failed: "Başarısız",
  skipped: "Atlandı",
};

const PAGE_SIZES = [20, 50, 100, 200] as const;
const TABLE_COL_COUNT = 7;

function toISODate(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function statusVariant(
  status: MediaStatus,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "processed") return "secondary";
  if (status === "failed") return "destructive";
  return "outline";
}

// ============================================================================

export default function AdminMediaPage() {
  const [data, setData] = useState<MediaImage[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<MediaStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [sources, setSources] = useState<SourcePublic[]>([]);

  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [dateRange, setDateRange] = useState<DateRange | undefined>(undefined);
  const [pageSize, setPageSize] = useState<number>(50);
  const [page, setPage] = useState<number>(1);
  const [today] = useState(() => new Date());

  // Filtre değişince sayfa 1'e dön
  useEffect(() => {
    setPage(1);
  }, [statusFilter, sourceFilter, dateRange, pageSize]);

  // Kaynaklar — bir kez yüklenir
  useEffect(() => {
    void (async () => {
      try {
        const list = await listSources({ limit: 200 });
        setSources(list);
      } catch {
        // sessiz
      }
    })();
  }, []);

  async function loadStats() {
    setStatsLoading(true);
    try {
      const s = await adminMediaStats();
      setStats(s);
    } catch (err) {
      toast.error((err as ApiException).message || "İstatistik yüklenemedi");
    } finally {
      setStatsLoading(false);
    }
  }

  async function loadList() {
    setLoading(true);
    try {
      const filters: MediaListFilters = {
        limit: pageSize,
        offset: (page - 1) * pageSize,
      };
      if (statusFilter !== "all") filters.status = statusFilter as MediaStatus;
      if (sourceFilter !== "all") filters.source_id = sourceFilter;
      if (dateRange?.from) filters.date_from = toISODate(dateRange.from);
      if (dateRange?.to) filters.date_to = toISODate(dateRange.to);

      const resp = await listAdminMedia(filters);
      setData(resp.data);
      setTotal(resp.total);
    } catch (err) {
      toast.error((err as ApiException).message || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, sourceFilter, dateRange, pageSize, page]);

  useEffect(() => {
    void loadStats();
  }, []);

  async function onReprocess(id: string) {
    try {
      await reprocessMedia(id);
      toast.success("Görsel kuyruğa eklendi");
      await Promise.all([loadList(), loadStats()]);
    } catch (err) {
      toast.error((err as ApiException).message || "Yeniden işleme başarısız");
    }
  }

  function handleRefresh() {
    void Promise.all([loadList(), loadStats()]);
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const pageStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const pageEnd = Math.min(total, page * pageSize);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Görseller"
        description="NIM Llama 4 Maverick (VLM) ile işlenen haber görselleri. Bytes saklanmaz; sadece vlm_caption + ocr_text + depicts metadata kalır (process & discard)."
      />

      {/* 4'lü stat grid */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Toplam görsel"
          value={stats?.total ?? null}
          loading={statsLoading}
        />
        <StatCard
          label="İşlenen"
          value={stats?.processed ?? null}
          loading={statsLoading}
          tone="success"
          subtitle={
            stats
              ? `Son 24s: ${stats.last_24h_processed.toLocaleString("tr-TR")}`
              : undefined
          }
        />
        <StatCard
          label="Bekleyen"
          value={stats?.pending ?? null}
          loading={statsLoading}
          tone="muted"
        />
        <StatCard
          label="Başarısız"
          value={stats?.failed ?? null}
          loading={statsLoading}
          tone={stats && stats.failed > 0 ? "destructive" : "muted"}
          subtitle={
            stats ? `Atlanan: ${stats.skipped.toLocaleString("tr-TR")}` : undefined
          }
        />
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
              <SelectItem value="pending">Bekliyor</SelectItem>
              <SelectItem value="processed">İşlendi</SelectItem>
              <SelectItem value="failed">Başarısız</SelectItem>
              <SelectItem value="skipped">Atlandı</SelectItem>
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

          <Popover>
            <PopoverTrigger
              type="button"
              data-size="sm"
              className="flex h-8 w-fit items-center gap-1.5 rounded-3xl border border-transparent bg-input/50 px-3 text-sm whitespace-nowrap transition-[color,box-shadow,background-color] outline-none hover:bg-muted focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 aria-expanded:bg-muted data-placeholder:text-muted-foreground dark:bg-input/30 dark:hover:bg-input/50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4"
            >
              <CalendarIcon />
              {dateRange?.from ? (
                dateRange.to ? (
                  <>
                    {format(dateRange.from, "LLL dd, y", { locale: trDate })} –{" "}
                    {format(dateRange.to, "LLL dd, y", { locale: trDate })}
                  </>
                ) : (
                  format(dateRange.from, "LLL dd, y", { locale: trDate })
                )
              ) : (
                <span className="text-muted-foreground">Tarih aralığı</span>
              )}
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
              <Calendar
                mode="range"
                selected={dateRange}
                onSelect={setDateRange}
                numberOfMonths={2}
                defaultMonth={
                  new Date(today.getFullYear(), today.getMonth() - 1, 1)
                }
                endMonth={today}
                disabled={{ after: today }}
                locale={tr}
                weekStartsOn={1}
              />
              {dateRange?.from && (
                <div className="flex justify-end border-t p-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDateRange(undefined)}
                  >
                    Temizle
                  </Button>
                </div>
              )}
            </PopoverContent>
          </Popover>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          disabled={loading || statsLoading}
        >
          <RefreshCw
            className={cn((loading || statsLoading) && "animate-spin")}
          />
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
                  <TableHead className="w-20">Önizleme</TableHead>
                  <TableHead>Durum</TableHead>
                  <TableHead className="min-w-[280px]">VLM açıklama</TableHead>
                  <TableHead>Konular</TableHead>
                  <TableHead>Haber</TableHead>
                  <TableHead>İşlendi</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 6 }).map((_, i) => (
                    <TableRow key={`skeleton-${i}`}>
                      <TableCell colSpan={TABLE_COL_COUNT}>
                        <Skeleton className="h-12 w-full" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : data.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={TABLE_COL_COUNT}
                      className="h-32 text-center text-sm text-muted-foreground"
                    >
                      Filtreye uyan görsel yok.
                    </TableCell>
                  </TableRow>
                ) : (
                  data.map((img) => (
                    <TableRow key={img.id}>
                      <TableCell>
                        <a
                          href={img.original_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block size-14 overflow-hidden rounded-md border bg-muted"
                          aria-label="Orijinal görseli aç"
                        >
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={img.original_url}
                            alt={img.alt_text || img.vlm_caption || ""}
                            loading="lazy"
                            className="size-full object-cover"
                            onError={(e) => {
                              (e.currentTarget as HTMLImageElement).style.display =
                                "none";
                            }}
                          />
                        </a>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={statusVariant(img.status)}
                          className="font-mono"
                        >
                          {STATUS_LABEL[img.status] ?? img.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          {img.vlm_caption ? (
                            <p className="line-clamp-2 text-sm text-foreground">
                              {img.vlm_caption}
                            </p>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                              <ImageOff className="size-3" />
                              VLM çıktısı yok
                            </span>
                          )}
                          {img.alt_text && (
                            <p className="line-clamp-1 text-xs text-muted-foreground">
                              alt: {img.alt_text}
                            </p>
                          )}
                          {img.ocr_text && (
                            <p className="line-clamp-1 font-mono text-[10px] text-muted-foreground">
                              OCR: {img.ocr_text}
                            </p>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {img.depicts && img.depicts.length > 0 ? (
                          <div className="flex max-w-[180px] flex-wrap gap-1">
                            {img.depicts.slice(0, 4).map((d, i) => (
                              <Badge
                                key={i}
                                variant="outline"
                                className="text-[10px]"
                              >
                                {d}
                              </Badge>
                            ))}
                            {img.depicts.length > 4 && (
                              <Badge
                                variant="outline"
                                className="text-[10px] text-muted-foreground"
                              >
                                +{img.depicts.length - 4}
                              </Badge>
                            )}
                          </div>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex max-w-[220px] flex-col">
                          <a
                            href={
                              img.article_id
                                ? `/admin/articles/${img.article_id}`
                                : "#"
                            }
                            className="line-clamp-1 text-sm font-medium text-primary hover:underline underline-offset-4"
                            title={img.article_title || ""}
                          >
                            {img.article_title || "—"}
                          </a>
                          <span className="line-clamp-1 text-xs text-muted-foreground">
                            {img.source_name || "—"}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground whitespace-nowrap">
                        {img.processed_at
                          ? formatTrDateTime(img.processed_at)
                          : "—"}
                      </TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-7"
                              aria-label="İşlemler"
                            >
                              <MoreVertical />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => onReprocess(img.id)}
                            >
                              <RotateCcw className="mr-2 size-3.5" />
                              Yeniden işle
                            </DropdownMenuItem>
                            <DropdownMenuItem asChild>
                              <a
                                href={img.original_url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                Orijinali aç
                              </a>
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

          {/* Footer: count + page size + pagination */}
          <div className="flex flex-col items-start gap-3 border-t px-6 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <span className="text-muted-foreground">
                {loading ? (
                  <Skeleton className="inline-block h-3.5 w-32 align-middle" />
                ) : total === 0 ? (
                  "0 görsel"
                ) : (
                  <>
                    <span className="font-medium tabular-nums text-foreground">
                      {pageStart}–{pageEnd}
                    </span>{" "}
                    / {total.toLocaleString("tr-TR")} görsel
                  </>
                )}
              </span>
              <Select
                value={String(pageSize)}
                onValueChange={(v) => setPageSize(Number(v))}
              >
                <SelectTrigger size="sm" className="w-[120px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PAGE_SIZES.map((n) => (
                    <SelectItem key={n} value={String(n)}>
                      {n} / sayfa
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {totalPages > 1 && (
              <Pagination className="mx-0 w-auto justify-end">
                <PaginationContent>
                  <PaginationItem>
                    <PaginationPrevious
                      href="#"
                      text="Önceki"
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
                  <PaginationItem>
                    <PaginationLink href="#" isActive>
                      {page}
                    </PaginationLink>
                  </PaginationItem>
                  <PaginationItem>
                    <PaginationNext
                      href="#"
                      text="Sonraki"
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

// ============================================================================
// StatCard alt-bileşen
// ============================================================================

function StatCard({
  label,
  value,
  loading,
  subtitle,
  tone = "default",
}: {
  label: string;
  value: number | null;
  loading: boolean;
  subtitle?: string;
  tone?: "default" | "success" | "destructive" | "muted";
}) {
  return (
    <Card className="rounded-2xl py-0 shadow-none ring-[var(--border)]">
      <CardContent className="space-y-1.5 p-4">
        <div className="text-xs text-muted-foreground">{label}</div>
        {loading ? (
          <Skeleton className="h-7 w-16" />
        ) : (
          <div
            className={cn(
              "text-2xl font-medium tabular-nums",
              tone === "success" && "text-emerald-600",
              tone === "destructive" && "text-destructive",
              tone === "muted" && "text-foreground",
            )}
          >
            {(value ?? 0).toLocaleString("tr-TR")}
          </div>
        )}
        {subtitle && (
          <div className="text-xs text-muted-foreground">{subtitle}</div>
        )}
      </CardContent>
    </Card>
  );
}
