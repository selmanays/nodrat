"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { RefreshCw, Search, Trash2, ShieldCheck } from "lucide-react";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ApiException,
  getAdminUserStats,
  listAdminUsers,
  type AdminUserStatsResponse,
  type AdminUserSummary,
} from "@/lib/api";

const TIER_VARIANT: Record<
  string,
  "muted" | "warning" | "success" | "secondary" | "default"
> = {
  trial: "muted",
  free: "secondary",
  starter: "warning",
  pro: "success",
  agency_seat: "default",
};

const ROLE_VARIANT: Record<
  string,
  "muted" | "warning" | "success" | "error" | "default"
> = {
  user: "muted",
  super_admin: "default",
};

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<AdminUserStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [roleFilter, setRoleFilter] = useState("");
  const [tierFilter, setTierFilter] = useState("");
  const [activeFilter, setActiveFilter] = useState<string>("");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");

  async function load() {
    setLoading(true);
    try {
      const [list, statsResp] = await Promise.all([
        listAdminUsers({
          role: roleFilter || undefined,
          tier: tierFilter || undefined,
          is_active:
            activeFilter === "" ? undefined : activeFilter === "active",
          deleted: includeDeleted || undefined,
          q: search || undefined,
          limit: 100,
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
  }, [roleFilter, tierFilter, activeFilter, includeDeleted, search]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Kullanıcılar</h1>
          <p className="text-sm text-muted-foreground">
            {total} kullanıcı
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void load()}
          disabled={loading}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Yenile
        </Button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid gap-3 md:grid-cols-5">
          <Card>
            <CardContent className="p-4">
              <div className="text-2xl font-semibold">{stats.total}</div>
              <div className="text-xs text-muted-foreground">Toplam</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-2xl font-semibold text-emerald-700">
                {stats.active}
              </div>
              <div className="text-xs text-muted-foreground">Aktif</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-2xl font-semibold text-amber-700">
                {stats.inactive}
              </div>
              <div className="text-xs text-muted-foreground">Pasif</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-2xl font-semibold text-red-700">
                {stats.deleted}
              </div>
              <div className="text-xs text-muted-foreground">Silinmiş</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-2xl font-semibold">
                {stats.email_verified}
              </div>
              <div className="text-xs text-muted-foreground">
                E-posta doğrulanmış
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="flex flex-wrap items-end gap-4 py-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Rol
            </label>
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Hepsi</option>
              <option value="user">Kullanıcı</option>
              <option value="super_admin">Süper Admin</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Tier
            </label>
            <select
              value={tierFilter}
              onChange={(e) => setTierFilter(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Hepsi</option>
              <option value="trial">Trial</option>
              <option value="free">Free</option>
              <option value="starter">Starter</option>
              <option value="pro">Pro</option>
              <option value="agency_seat">Agency Seat</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Durum
            </label>
            <select
              value={activeFilter}
              onChange={(e) => setActiveFilter(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Hepsi</option>
              <option value="active">Aktif</option>
              <option value="inactive">Pasif</option>
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm pt-5 cursor-pointer">
            <input
              type="checkbox"
              checked={includeDeleted}
              onChange={(e) => setIncludeDeleted(e.target.checked)}
            />
            Silinmiş hesapları dahil et
          </label>
          <div className="flex-1 min-w-[240px] space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              E-posta arama
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
                placeholder="ornek@nodrat.com"
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
      ) : users.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Kullanıcı bulunamadı</CardTitle>
          </CardHeader>
        </Card>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Kullanıcı</TableHead>
                <TableHead>Rol</TableHead>
                <TableHead>Tier</TableHead>
                <TableHead>Durum</TableHead>
                <TableHead>Son giriş</TableHead>
                <TableHead>Kayıt</TableHead>
                <TableHead className="text-right">İşlem</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow
                  key={u.id}
                  className={u.deleted_at ? "bg-destructive/5" : undefined}
                >
                  <TableCell>
                    <div className="font-medium">{u.email}</div>
                    {u.full_name && (
                      <div className="text-xs text-muted-foreground">
                        {u.full_name}
                      </div>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={ROLE_VARIANT[u.role] ?? "muted"}>
                      {u.role === "super_admin" ? "Admin" : "Kullanıcı"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={TIER_VARIANT[u.tier] ?? "muted"}>
                      {u.tier}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {u.deleted_at ? (
                      <Badge variant="error">
                        <Trash2 className="mr-1 h-3 w-3" />
                        Silinmiş
                      </Badge>
                    ) : u.is_active ? (
                      <Badge variant="success">
                        {u.email_verified && (
                          <ShieldCheck className="mr-1 h-3 w-3" />
                        )}
                        Aktif
                      </Badge>
                    ) : (
                      <Badge variant="warning">Pasif</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {u.last_login_at
                      ? new Date(u.last_login_at).toLocaleString("tr-TR", {
                          day: "2-digit",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "—"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(u.created_at).toLocaleDateString("tr-TR")}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/admin/users/${u.id}`}>Detay</Link>
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
