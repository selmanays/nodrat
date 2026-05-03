"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ApiException,
  listAuditLog,
  type AuditLogEntry,
  type AuditLogFilters,
} from "@/lib/api";
import { formatTrDateTime } from "@/lib/format";

const ACTION_OPTIONS = [
  { value: "", label: "Tümü" },
  { value: "source.create", label: "source.create" },
  { value: "source.update", label: "source.update" },
  { value: "source.activate", label: "source.activate" },
  { value: "source.deactivate", label: "source.deactivate" },
  { value: "article.reprocess", label: "article.reprocess" },
  { value: "user.role_change", label: "user.role_change" },
  { value: "user.tier_change", label: "user.tier_change" },
  { value: "user.deactivate", label: "user.deactivate" },
  { value: "user.activate", label: "user.activate" },
  { value: "user.restore", label: "user.restore" },
  { value: "takedown.process", label: "takedown.process" },
  { value: "data_export", label: "data_export" },
  { value: "account_delete", label: "account_delete" },
  { value: "provider.config_change", label: "provider.config_change" },
];

const TARGET_TYPE_OPTIONS = [
  { value: "", label: "Tümü" },
  { value: "source", label: "source" },
  { value: "article", label: "article" },
  { value: "user", label: "user" },
  { value: "provider", label: "provider" },
  { value: "takedown_request", label: "takedown_request" },
];

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
      // Boş string'leri temizle
      const cleaned: AuditLogFilters = { limit: filters.limit, offset: filters.offset };
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

  // fmtDate → lib/format.formatTrDateTime (Europe/Istanbul, #232)

  function actionVariant(
    action: string,
  ): "outline" | "success" | "error" | "warning" | "default" {
    if (action.endsWith(".activate") || action.endsWith(".restore")) return "success";
    if (action.endsWith(".deactivate") || action.includes("delete")) return "error";
    if (
      action.endsWith(".update") ||
      action.includes("role_change") ||
      action.includes("tier_change")
    )
      return "warning";
    if (action.startsWith("takedown.")) return "default";
    return "outline";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Audit log</h1>
          <p className="text-sm text-muted-foreground">
            Admin işlem kayıtları (KVKK §8.3 transparency)
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

      {/* Filters */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Filtre</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">Action</label>
            <select
              value={filters.action || ""}
              onChange={(e) =>
                setFilters({ ...filters, action: e.target.value || undefined, offset: 0 })
              }
              className="w-full rounded-md border bg-background px-3 py-1.5 text-sm"
            >
              {ACTION_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">
              Target type
            </label>
            <select
              value={filters.target_type || ""}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  target_type: e.target.value || undefined,
                  offset: 0,
                })
              }
              className="w-full rounded-md border bg-background px-3 py-1.5 text-sm"
            >
              {TARGET_TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">
              Actor ID (UUID)
            </label>
            <input
              type="text"
              value={filters.actor_id || ""}
              onChange={(e) =>
                setFilters({ ...filters, actor_id: e.target.value || undefined, offset: 0 })
              }
              placeholder="00000000-..."
              className="w-full rounded-md border bg-background px-3 py-1.5 text-sm font-mono"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">
              Tarih (≥)
            </label>
            <input
              type="date"
              value={filters.date_from || ""}
              onChange={(e) =>
                setFilters({ ...filters, date_from: e.target.value || undefined, offset: 0 })
              }
              className="w-full rounded-md border bg-background px-3 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">
              Tarih (&lt;)
            </label>
            <input
              type="date"
              value={filters.date_to || ""}
              onChange={(e) =>
                setFilters({ ...filters, date_to: e.target.value || undefined, offset: 0 })
              }
              className="w-full rounded-md border bg-background px-3 py-1.5 text-sm"
            />
          </div>
        </CardContent>
      </Card>

      {/* Result */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">
            {loading ? "Yükleniyor…" : `${total.toLocaleString("tr-TR")} kayıt`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {data.length === 0 && !loading ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              Filtrelere uyan kayıt yok.
            </p>
          ) : (
            <div className="space-y-1">
              {data.map((entry) => {
                const isExpanded = expanded.has(entry.id);
                const hasMetadata =
                  entry.event_metadata && Object.keys(entry.event_metadata).length > 0;
                return (
                  <div
                    key={entry.id}
                    className="border rounded-md p-3 text-sm"
                  >
                    <div className="flex items-start gap-3">
                      <button
                        type="button"
                        onClick={() => hasMetadata && toggleExpand(entry.id)}
                        disabled={!hasMetadata}
                        className="mt-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-default"
                      >
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </button>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge variant={actionVariant(entry.action)} className="font-mono text-xs">
                            {entry.action}
                          </Badge>
                          {entry.target_type && (
                            <Badge variant="outline" className="font-mono text-xs">
                              {entry.target_type}
                            </Badge>
                          )}
                          <span className="text-xs text-muted-foreground">
                            {formatTrDateTime(entry.created_at)}
                          </span>
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground flex flex-wrap gap-3">
                          <span>
                            <span className="font-medium">{entry.actor_email || "?"}</span>
                            {" — "}
                            <span className="font-mono">
                              {entry.actor_id.slice(0, 8)}…
                            </span>
                          </span>
                          {entry.target_id && (
                            <span className="font-mono">
                              target: {entry.target_id.slice(0, 8)}…
                            </span>
                          )}
                          {entry.ip_address && (
                            <span className="font-mono">{entry.ip_address}</span>
                          )}
                        </div>
                        {isExpanded && hasMetadata && (
                          <pre className="mt-2 p-2 rounded bg-muted text-xs overflow-x-auto font-mono">
                            {JSON.stringify(entry.event_metadata, null, 2)}
                          </pre>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination */}
          {total > (filters.limit ?? 50) && (
            <div className="mt-4 flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                {(filters.offset ?? 0) + 1}–
                {Math.min((filters.offset ?? 0) + (filters.limit ?? 50), total)} / {total}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={(filters.offset ?? 0) === 0 || loading}
                  onClick={() =>
                    setFilters({
                      ...filters,
                      offset: Math.max(0, (filters.offset ?? 0) - (filters.limit ?? 50)),
                    })
                  }
                >
                  Önceki
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={
                    (filters.offset ?? 0) + (filters.limit ?? 50) >= total || loading
                  }
                  onClick={() =>
                    setFilters({
                      ...filters,
                      offset: (filters.offset ?? 0) + (filters.limit ?? 50),
                    })
                  }
                >
                  Sonraki
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
