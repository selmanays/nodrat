"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ExternalLink, MoreVertical, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";

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
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageHeader } from "@/components/blocks/page-header";
import { formatTrDate, formatTrDateOnly } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  ApiException,
  getAdminUserStats,
  listAdminUsers,
  type AdminUserStatsResponse,
  type AdminUserSummary,
} from "@/lib/api";

const PAGE_SIZES = [10, 20, 50, 100] as const;

const ROLE_LABEL: Record<string, string> = {
  user: "Kullanıcı",
  super_admin: "Süper admin",
};

const TIER_LABEL: Record<string, string> = {
  trial: "Deneme",
  free: "Ücretsiz",
  starter: "Başlangıç",
  pro: "Pro",
  agency_seat: "Ajans",
};

// #233 — tariSaatBicimle / tarihBicimle yerel fonksiyonları kaldırıldı,
// formatTrDate / formatTrDateOnly kullanılıyor (Europe/Istanbul TZ-aware)

function DurumRozeti({ user }: { user: AdminUserSummary }) {
  if (user.deleted_at) {
    return (
      <Badge variant="outline" className="h-5.5">
        Silinmiş
      </Badge>
    );
  }
  if (!user.is_active) {
    return (
      <Badge variant="outline" className="h-5.5">
        Pasif
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="h-5.5">
      Aktif
    </Badge>
  );
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [stats, setStats] = useState<AdminUserStatsResponse | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const [roleFilter, setRoleFilter] = useState<string>("all");
  const [tierFilter, setTierFilter] = useState<string>("all");
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(20);

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchInput), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Filter değişince sayfa 1'e dön
  useEffect(() => {
    setPage(1);
  }, [
    roleFilter,
    tierFilter,
    activeFilter,
    includeDeleted,
    debouncedSearch,
    pageSize,
  ]);

  async function load() {
    setLoading(true);
    try {
      const [list, statsResp] = await Promise.all([
        listAdminUsers({
          role: roleFilter === "all" ? undefined : roleFilter,
          tier: tierFilter === "all" ? undefined : tierFilter,
          is_active:
            activeFilter === "all"
              ? undefined
              : activeFilter === "active",
          deleted: includeDeleted || undefined,
          q: debouncedSearch || undefined,
          limit: pageSize,
          offset: (page - 1) * pageSize,
        }),
        getAdminUserStats(),
      ]);
      setUsers(list.data);
      setTotal(list.total);
      setStats(statsResp);
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
    roleFilter,
    tierFilter,
    activeFilter,
    includeDeleted,
    debouncedSearch,
    page,
    pageSize,
  ]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const pageStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const pageEnd = Math.min(total, page * pageSize);

  const pageNumbers = useMemo(() => {
    const range: (number | "...")[] = [];
    const add = (n: number) => {
      if (!range.includes(n)) range.push(n);
    };
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) add(i);
    } else {
      add(1);
      if (page > 3) range.push("...");
      for (
        let i = Math.max(2, page - 1);
        i <= Math.min(totalPages - 1, page + 1);
        i++
      ) {
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
        title="Kullanıcılar"
        description="Hesapları yönet, rol ve abonelik seviyesini düzenle, hesap durumlarını izle."
      />

      {/* Stats summary */}
      <div className="grid grid-cols-2 gap-4 pb-4 md:grid-cols-5">
        {loading && !stats
          ? Array.from({ length: 5 }).map((_, i) => (
              <Card
                key={i}
                className="rounded-2xl py-0 shadow-none ring-[var(--border)]"
              >
                <CardContent className="p-4">
                  <Skeleton className="h-7 w-12" />
                  <Skeleton className="mt-2 h-3 w-20" />
                </CardContent>
              </Card>
            ))
          : stats && (
              <>
                <Card className="rounded-2xl py-0 shadow-none ring-[var(--border)]">
                  <CardContent className="p-4">
                    <div className="text-2xl font-semibold tabular-nums">
                      {stats.total.toLocaleString("tr-TR")}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Toplam
                    </div>
                  </CardContent>
                </Card>
                <Card className="rounded-2xl py-0 shadow-none ring-[var(--border)]">
                  <CardContent className="p-4">
                    <div className="text-2xl font-semibold tabular-nums">
                      {stats.active.toLocaleString("tr-TR")}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Aktif
                    </div>
                  </CardContent>
                </Card>
                <Card className="rounded-2xl py-0 shadow-none ring-[var(--border)]">
                  <CardContent className="p-4">
                    <div className="text-2xl font-semibold tabular-nums">
                      {stats.inactive.toLocaleString("tr-TR")}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Pasif
                    </div>
                  </CardContent>
                </Card>
                <Card className="rounded-2xl py-0 shadow-none ring-[var(--border)]">
                  <CardContent className="p-4">
                    <div className="text-2xl font-semibold tabular-nums">
                      {stats.deleted.toLocaleString("tr-TR")}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Silinmiş
                    </div>
                  </CardContent>
                </Card>
                <Card className="rounded-2xl py-0 shadow-none ring-[var(--border)]">
                  <CardContent className="p-4">
                    <div className="text-2xl font-semibold tabular-nums">
                      {stats.email_verified.toLocaleString("tr-TR")}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      E-posta doğrulanmış
                    </div>
                  </CardContent>
                </Card>
              </>
            )}
      </div>

      {/* Filtreler ve yenile butonu */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="E-posta ara…"
              className="h-8 w-[240px] pl-8 text-sm"
            />
          </div>
          <Select value={roleFilter} onValueChange={setRoleFilter}>
            <SelectTrigger size="sm" className="w-[150px]">
              <SelectValue placeholder="Rol" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tüm roller</SelectItem>
              <SelectItem value="user">Kullanıcı</SelectItem>
              <SelectItem value="super_admin">Süper admin</SelectItem>
            </SelectContent>
          </Select>
          <Select value={tierFilter} onValueChange={setTierFilter}>
            <SelectTrigger size="sm" className="w-[160px]">
              <SelectValue placeholder="Tier" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tüm seviyeler</SelectItem>
              {Object.entries(TIER_LABEL).map(([k, v]) => (
                <SelectItem key={k} value={k}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={activeFilter} onValueChange={setActiveFilter}>
            <SelectTrigger size="sm" className="w-[150px]">
              <SelectValue placeholder="Durum" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tüm durumlar</SelectItem>
              <SelectItem value="active">Aktif</SelectItem>
              <SelectItem value="inactive">Pasif</SelectItem>
            </SelectContent>
          </Select>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <Switch
              checked={includeDeleted}
              onCheckedChange={setIncludeDeleted}
            />
            <span>Silinmişleri dahil et</span>
          </label>
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
                  <TableHead className="px-6">Kullanıcı</TableHead>
                  <TableHead>Rol</TableHead>
                  <TableHead>Tier</TableHead>
                  <TableHead>Durum</TableHead>
                  <TableHead>Son giriş</TableHead>
                  <TableHead>Kayıt</TableHead>
                  <TableHead className="px-6 text-right">İşlem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 8 }).map((_, i) => (
                    <TableRow key={i}>
                      <TableCell className="px-6">
                        <Skeleton className="h-4 w-48" />
                        <Skeleton className="mt-1.5 h-3 w-32" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-20" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-16" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-16" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-3 w-24" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-3 w-20" />
                      </TableCell>
                      <TableCell className="px-6 text-right">
                        <Skeleton className="ml-auto size-8 rounded-full" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : users.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="h-32 text-center text-sm text-muted-foreground"
                    >
                      Filtreye uyan kullanıcı yok.
                    </TableCell>
                  </TableRow>
                ) : (
                  users.map((u) => (
                    <TableRow
                      key={u.id}
                      className={
                        u.deleted_at ? "bg-destructive/5" : undefined
                      }
                    >
                      <TableCell className="px-6">
                        <div className="font-medium">{u.email}</div>
                        {u.full_name && (
                          <div className="text-xs text-muted-foreground">
                            {u.full_name}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="h-5.5">
                          {ROLE_LABEL[u.role] ?? u.role}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="h-5.5">
                          {TIER_LABEL[u.tier] ?? u.tier}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <DurumRozeti user={u} />
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatTrDate(u.last_login_at)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatTrDateOnly(u.created_at)}
                      </TableCell>
                      <TableCell className="px-6 text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger
                            aria-label={`${u.email} işlemleri`}
                            className="ml-auto inline-flex size-8 items-center justify-center rounded-full text-muted-foreground transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 data-[state=open]:bg-muted data-[state=open]:text-foreground [&_svg]:size-4 [&_svg]:shrink-0"
                          >
                            <MoreVertical />
                            <span className="sr-only">İşlemler</span>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem asChild>
                              <Link href={`/admin/users/${u.id}`}>
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

          {/* Footer */}
          <div className="flex flex-col items-start gap-3 border-t px-6 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <span className="text-muted-foreground">
                {loading ? (
                  <Skeleton className="inline-block h-3.5 w-32 align-middle" />
                ) : total === 0 ? (
                  "0 kullanıcı"
                ) : (
                  <>
                    <span className="font-medium tabular-nums text-foreground">
                      {pageStart}–{pageEnd}
                    </span>{" "}
                    / {total.toLocaleString("tr-TR")} kullanıcı
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
                      text="Sonraki"
                      onClick={(e) => {
                        e.preventDefault();
                        if (page < totalPages) setPage(page + 1);
                      }}
                      aria-disabled={page >= totalPages}
                      className={cn(
                        page >= totalPages &&
                          "pointer-events-none opacity-50",
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
