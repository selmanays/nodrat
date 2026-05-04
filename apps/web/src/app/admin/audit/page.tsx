"use client";

import { Fragment, useEffect, useState } from "react";
import {
  CalendarIcon,
  ChevronDown,
  ChevronRight,
  RefreshCw,
} from "lucide-react";
import { tr } from "react-day-picker/locale";
import type { DateRange } from "react-day-picker";
import { toast } from "sonner";

import { PageHeader } from "@/components/blocks/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Card, CardContent } from "@/components/ui/card";
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
import {
  ApiException,
  listAuditLog,
  type AuditLogEntry,
  type AuditLogFilters,
} from "@/lib/api";
import { formatTrDateTime } from "@/lib/format";

// ============================================================================
// Türkçe etiketler (Badge orijinal enum'u korur, dropdown Türkçe görünür)
// ============================================================================

const ACTION_LABEL: Record<string, string> = {
  "source.create": "Kaynak oluşturma",
  "source.update": "Kaynak güncelleme",
  "source.activate": "Kaynak aktifleştirme",
  "source.deactivate": "Kaynak pasifleştirme",
  "article.reprocess": "Haber yeniden işleme",
  "user.role_change": "Kullanıcı rolü değişikliği",
  "user.tier_change": "Kullanıcı tier değişikliği",
  "user.deactivate": "Kullanıcı pasifleştirme",
  "user.activate": "Kullanıcı aktifleştirme",
  "user.restore": "Kullanıcı geri yükleme",
  "takedown.process": "Kaldırma talebi işleme",
  data_export: "Veri dışa aktarma",
  account_delete: "Hesap silme",
  "provider.config_change": "Sağlayıcı yapılandırma",
};

const TARGET_TYPE_LABEL: Record<string, string> = {
  source: "Kaynak",
  article: "Haber",
  user: "Kullanıcı",
  provider: "Sağlayıcı",
  takedown_request: "Kaldırma talebi",
};

const PAGE_SIZES = [10, 20, 50, 100] as const;
const TABLE_COL_COUNT = 7;

function toISODate(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatRangeLabel(range: DateRange | undefined): string {
  if (!range?.from) return "Tarih aralığı";
  const fromTxt = range.from.toLocaleDateString("tr-TR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  if (!range.to) return fromTxt;
  const toTxt = range.to.toLocaleDateString("tr-TR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  return `${fromTxt} – ${toTxt}`;
}

function actionVariant(
  action: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (action.endsWith(".activate") || action.endsWith(".restore"))
    return "secondary";
  if (action.endsWith(".deactivate") || action.includes("delete"))
    return "destructive";
  if (
    action.endsWith(".update") ||
    action.includes("role_change") ||
    action.includes("tier_change")
  )
    return "outline";
  if (action.startsWith("takedown.")) return "default";
  return "outline";
}

// ============================================================================

export default function AdminAuditLogPage() {
  const [data, setData] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const [actionFilter, setActionFilter] = useState<string>("all");
  const [targetTypeFilter, setTargetTypeFilter] = useState<string>("all");
  const [actorIdInput, setActorIdInput] = useState<string>("");
  const [debouncedActorId, setDebouncedActorId] = useState<string>("");
  const [dateRange, setDateRange] = useState<DateRange | undefined>(undefined);
  const [pageSize, setPageSize] = useState<number>(50);
  const [page, setPage] = useState<number>(1);
  const [today] = useState(() => new Date());

  // Debounce actor id
  useEffect(() => {
    const t = setTimeout(() => setDebouncedActorId(actorIdInput.trim()), 300);
    return () => clearTimeout(t);
  }, [actorIdInput]);

  // Filtre değişince sayfa 1'e dön
  useEffect(() => {
    setPage(1);
  }, [actionFilter, targetTypeFilter, debouncedActorId, dateRange, pageSize]);

  async function load() {
    setLoading(true);
    try {
      const filters: AuditLogFilters = {
        limit: pageSize,
        offset: (page - 1) * pageSize,
      };
      if (actionFilter !== "all") filters.action = actionFilter;
      if (targetTypeFilter !== "all") filters.target_type = targetTypeFilter;
      if (debouncedActorId) filters.actor_id = debouncedActorId;
      if (dateRange?.from) filters.date_from = toISODate(dateRange.from);
      if (dateRange?.to) filters.date_to = toISODate(dateRange.to);

      const resp = await listAuditLog(filters);
      setData(resp.data);
      setTotal(resp.total);
    } catch (err) {
      toast.error((err as ApiException).message || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    actionFilter,
    targetTypeFilter,
    debouncedActorId,
    dateRange,
    pageSize,
    page,
  ]);

  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const pageStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const pageEnd = Math.min(total, page * pageSize);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Denetim"
        description="Sistem yöneticisi işlem kayıtları (KVKK §8.3 şeffaflık). Her eylemde aktör, hedef ve metadata izlenir."
      />

      {/* Filtreler ve yenile butonu — kart dışında */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={actorIdInput}
            onChange={(e) => setActorIdInput(e.target.value)}
            placeholder="Aktör UUID ara…"
            className="h-8 w-[220px] text-sm"
          />
          <Select value={actionFilter} onValueChange={setActionFilter}>
            <SelectTrigger size="sm" className="w-[200px]">
              <SelectValue placeholder="Eylem" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tüm eylemler</SelectItem>
              {Object.entries(ACTION_LABEL).map(([k, v]) => (
                <SelectItem key={k} value={k}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={targetTypeFilter}
            onValueChange={setTargetTypeFilter}
          >
            <SelectTrigger size="sm" className="w-[160px]">
              <SelectValue placeholder="Hedef türü" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tüm türler</SelectItem>
              {Object.entries(TARGET_TYPE_LABEL).map(([k, v]) => (
                <SelectItem key={k} value={k}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Popover>
            <PopoverTrigger asChild>
              <div className="relative">
                <Input
                  readOnly
                  value={
                    dateRange?.from
                      ? formatRangeLabel(dateRange)
                      : "Tarih aralığı"
                  }
                  className="h-8 w-fit min-w-[140px] pr-8 text-sm"
                  size={
                    dateRange?.from
                      ? formatRangeLabel(dateRange).length + 2
                      : 14
                  }
                />
                <CalendarIcon
                  className="pointer-events-none absolute top-1/2 right-3 size-3.5 -translate-y-1/2 text-muted-foreground"
                />
              </div>
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
                  <TableHead className="w-9" />
                  <TableHead>Eylem</TableHead>
                  <TableHead>Hedef türü</TableHead>
                  <TableHead>Aktör</TableHead>
                  <TableHead>Hedef ID</TableHead>
                  <TableHead>IP</TableHead>
                  <TableHead>Zaman</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 6 }).map((_, i) => (
                    <TableRow key={`skeleton-${i}`}>
                      <TableCell colSpan={TABLE_COL_COUNT}>
                        <Skeleton className="h-5 w-full" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : data.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={TABLE_COL_COUNT}
                      className="h-32 text-center text-sm text-muted-foreground"
                    >
                      Filtreye uyan kayıt yok.
                    </TableCell>
                  </TableRow>
                ) : (
                  data.map((entry) => {
                    const isExpanded = expanded.has(entry.id);
                    const hasMetadata =
                      entry.event_metadata &&
                      Object.keys(entry.event_metadata).length > 0;
                    return (
                      <Fragment key={entry.id}>
                        <TableRow
                          data-state={isExpanded ? "selected" : undefined}
                          className={cn(hasMetadata && "cursor-pointer")}
                          onClick={() =>
                            hasMetadata && toggleExpand(entry.id)
                          }
                        >
                          <TableCell className="w-9 align-middle">
                            {hasMetadata ? (
                              <Button
                                variant="ghost"
                                size="icon"
                                aria-label={
                                  isExpanded ? "Detayı kapat" : "Detayı aç"
                                }
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleExpand(entry.id);
                                }}
                                className="size-7"
                              >
                                {isExpanded ? (
                                  <ChevronDown />
                                ) : (
                                  <ChevronRight />
                                )}
                              </Button>
                            ) : (
                              <span className="block size-7" aria-hidden />
                            )}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={actionVariant(entry.action)}
                              className="font-mono"
                            >
                              {entry.action}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            {entry.target_type ? (
                              <Badge variant="outline" className="font-mono">
                                {entry.target_type}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                          <TableCell>
                            <div className="flex flex-col">
                              <span className="font-medium">
                                {entry.actor_email || "—"}
                              </span>
                              <span className="font-mono text-xs text-muted-foreground">
                                {entry.actor_id.slice(0, 8)}…
                              </span>
                            </div>
                          </TableCell>
                          <TableCell>
                            {entry.target_id ? (
                              <span className="font-mono text-xs">
                                {entry.target_id.slice(0, 8)}…
                              </span>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                          <TableCell>
                            {entry.ip_address ? (
                              <span className="font-mono text-xs">
                                {entry.ip_address}
                              </span>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {formatTrDateTime(entry.created_at)}
                          </TableCell>
                        </TableRow>
                        {isExpanded && hasMetadata && (
                          <TableRow
                            data-state="selected"
                            className="hover:bg-transparent"
                          >
                            <TableCell />
                            <TableCell
                              colSpan={TABLE_COL_COUNT - 1}
                              className="p-0"
                            >
                              <div className="space-y-2 bg-muted/30 p-4">
                                {entry.user_agent && (
                                  <div className="text-xs text-muted-foreground">
                                    <span className="font-medium">
                                      User-Agent:
                                    </span>{" "}
                                    <span className="font-mono">
                                      {entry.user_agent}
                                    </span>
                                  </div>
                                )}
                                <div>
                                  <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                                    Olay metadata (JSON)
                                  </p>
                                  <pre className="max-h-96 overflow-auto rounded-lg border bg-background p-3 font-mono text-xs leading-relaxed">
                                    {JSON.stringify(
                                      entry.event_metadata,
                                      null,
                                      2,
                                    )}
                                  </pre>
                                </div>
                              </div>
                            </TableCell>
                          </TableRow>
                        )}
                      </Fragment>
                    );
                  })
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
                  "0 kayıt"
                ) : (
                  <>
                    <span className="font-medium tabular-nums text-foreground">
                      {pageStart}–{pageEnd}
                    </span>{" "}
                    / {total.toLocaleString("tr-TR")} kayıt
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
