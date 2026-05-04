"use client";

import { Fragment, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/blocks/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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

const ACTION_OPTIONS = [
  { value: "all", label: "Tüm eylemler" },
  ...Object.keys(ACTION_LABEL).map((value) => ({
    value,
    label: ACTION_LABEL[value],
  })),
];

const TARGET_TYPE_OPTIONS = [
  { value: "all", label: "Tüm türler" },
  ...Object.keys(TARGET_TYPE_LABEL).map((value) => ({
    value,
    label: TARGET_TYPE_LABEL[value],
  })),
];

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

const TABLE_COL_COUNT = 7;

// ============================================================================

export default function AdminAuditLogPage() {
  const [data, setData] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const [filters, setFilters] = useState<AuditLogFilters>({
    limit: 50,
    offset: 0,
  });

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filters)]);

  async function load() {
    setLoading(true);
    try {
      const cleaned: AuditLogFilters = {
        limit: filters.limit,
        offset: filters.offset,
      };
      if (filters.action) cleaned.action = filters.action;
      if (filters.target_type) cleaned.target_type = filters.target_type;
      if (filters.actor_id) cleaned.actor_id = filters.actor_id;
      if (filters.date_from) cleaned.date_from = filters.date_from;
      if (filters.date_to) cleaned.date_to = filters.date_to;

      const resp = await listAuditLog(cleaned);
      setData(resp.data);
      setTotal(resp.total);
    } catch (err) {
      toast.error((err as ApiException).message || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
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

  const limit = filters.limit ?? 50;
  const offset = filters.offset ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const currentPage = Math.floor(offset / limit) + 1;
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + limit, total);

  function goToPage(page: number) {
    const next = Math.max(1, Math.min(totalPages, page));
    setFilters({ ...filters, offset: (next - 1) * limit });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Denetim"
        description="Sistem yöneticisi işlem kayıtları (KVKK §8.3 şeffaflık). Her eylemde aktör, hedef ve metadata izlenir."
        action={
          <Button
            variant="outline"
            size="sm"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw
              className={loading ? "animate-spin" : undefined}
              data-icon="inline-start"
            />
            Yenile
          </Button>
        }
      />

      {/* Filtre satırı — kart dışı */}
      <div className="flex flex-col gap-2 pb-4 lg:flex-row lg:flex-wrap lg:items-center">
        <Input
          value={filters.actor_id || ""}
          onChange={(e) =>
            setFilters({
              ...filters,
              actor_id: e.target.value || undefined,
              offset: 0,
            })
          }
          placeholder="Aktör UUID ile ara…"
          className="w-full font-mono lg:w-72"
        />

        <Select
          value={filters.action ?? "all"}
          onValueChange={(v) =>
            setFilters({
              ...filters,
              action: v === "all" ? undefined : v,
              offset: 0,
            })
          }
        >
          <SelectTrigger className="w-full lg:w-56" aria-label="Eylem">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ACTION_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.target_type ?? "all"}
          onValueChange={(v) =>
            setFilters({
              ...filters,
              target_type: v === "all" ? undefined : v,
              offset: 0,
            })
          }
        >
          <SelectTrigger className="w-full lg:w-44" aria-label="Hedef türü">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TARGET_TYPE_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-2 lg:ml-auto">
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            Başlangıç
            <Input
              type="date"
              value={filters.date_from || ""}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  date_from: e.target.value || undefined,
                  offset: 0,
                })
              }
              className="w-[10.5rem]"
            />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            Bitiş
            <Input
              type="date"
              value={filters.date_to || ""}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  date_to: e.target.value || undefined,
                  offset: 0,
                })
              }
              className="w-[10.5rem]"
            />
          </label>
        </div>
      </div>

      {/* Tablo + collapsible JSON */}
      <Card className="overflow-hidden rounded-2xl py-0 shadow-none ring-[var(--border)]">
        <Table>
          <TableHeader className="bg-muted/50">
            <TableRow>
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
                    <Skeleton className="h-6 w-full" />
                  </TableCell>
                </TableRow>
              ))
            ) : data.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={TABLE_COL_COUNT}
                  className="py-10 text-center text-sm text-muted-foreground"
                >
                  Filtrelere uyan kayıt yok.
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
                      className={
                        hasMetadata
                          ? "cursor-pointer"
                          : undefined
                      }
                      onClick={() => hasMetadata && toggleExpand(entry.id)}
                    >
                      <TableCell className="w-9 align-middle">
                        {hasMetadata ? (
                          <button
                            type="button"
                            aria-label={
                              isExpanded ? "Detayı kapat" : "Detayı aç"
                            }
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpand(entry.id);
                            }}
                            className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                          >
                            {isExpanded ? (
                              <ChevronDown className="size-4" />
                            ) : (
                              <ChevronRight className="size-4" />
                            )}
                          </button>
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
                      <TableCell className="text-xs text-muted-foreground">
                        {formatTrDateTime(entry.created_at)}
                      </TableCell>
                    </TableRow>
                    {isExpanded && hasMetadata && (
                      <TableRow data-state="selected" className="hover:bg-transparent">
                        <TableCell />
                        <TableCell colSpan={TABLE_COL_COUNT - 1} className="p-0">
                          <div className="space-y-2 border-l-2 border-primary/40 bg-muted/30 p-4">
                            {entry.user_agent && (
                              <div className="text-xs text-muted-foreground">
                                <span className="font-medium">User-Agent:</span>{" "}
                                <span className="font-mono">
                                  {entry.user_agent}
                                </span>
                              </div>
                            )}
                            <div>
                              <p className="mb-1 text-xs font-medium text-muted-foreground">
                                Olay metadata (JSON)
                              </p>
                              <pre className="max-h-96 overflow-auto rounded-lg border bg-background p-3 font-mono text-xs leading-relaxed">
                                {JSON.stringify(entry.event_metadata, null, 2)}
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

        {/* Footer: count + page size + pagination */}
        <div className="flex flex-col items-stretch gap-3 border-t px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground">
            {total === 0
              ? "Kayıt yok"
              : `${rangeStart.toLocaleString("tr-TR")}–${rangeEnd.toLocaleString(
                  "tr-TR",
                )} / ${total.toLocaleString("tr-TR")} kayıt`}
          </p>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Sayfada</span>
              <Select
                value={String(limit)}
                onValueChange={(v) =>
                  setFilters({ ...filters, limit: Number(v), offset: 0 })
                }
              >
                <SelectTrigger size="sm" className="w-20" aria-label="Sayfa boyutu">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PAGE_SIZE_OPTIONS.map((n) => (
                    <SelectItem key={n} value={String(n)}>
                      {n}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <Pagination className="w-auto justify-end">
              <PaginationContent>
                <PaginationItem>
                  <PaginationPrevious
                    text="Önceki"
                    aria-disabled={currentPage <= 1 || loading}
                    onClick={(e) => {
                      e.preventDefault();
                      if (currentPage > 1 && !loading) goToPage(currentPage - 1);
                    }}
                    className={
                      currentPage <= 1 || loading
                        ? "pointer-events-none opacity-50"
                        : "cursor-pointer"
                    }
                  />
                </PaginationItem>
                <PaginationItem>
                  <PaginationLink isActive aria-current="page">
                    {currentPage}
                  </PaginationLink>
                </PaginationItem>
                <PaginationItem>
                  <PaginationNext
                    text="Sonraki"
                    aria-disabled={currentPage >= totalPages || loading}
                    onClick={(e) => {
                      e.preventDefault();
                      if (currentPage < totalPages && !loading)
                        goToPage(currentPage + 1);
                    }}
                    className={
                      currentPage >= totalPages || loading
                        ? "pointer-events-none opacity-50"
                        : "cursor-pointer"
                    }
                  />
                </PaginationItem>
              </PaginationContent>
            </Pagination>
          </div>
        </div>
      </Card>
    </div>
  );
}
