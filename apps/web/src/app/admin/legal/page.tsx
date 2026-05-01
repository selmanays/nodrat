"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiException,
  listTakedownRequests,
  type TakedownAdminPublic,
} from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  abuse: "Kötüye kullanım",
  takedown: "5651 Kaldırma",
  copyright: "FSEK Telif",
  privacy_request: "KVKK md.11",
};

const STATUS_LABEL: Record<string, string> = {
  submitted: "Yeni",
  triaging: "Triajda",
  investigating: "İnceleniyor",
  action_taken: "Aksiyon alındı",
  rejected: "Reddedildi",
  closed: "Kapalı",
};

const STATUS_VARIANT: Record<
  string,
  "muted" | "warning" | "success" | "error" | "secondary"
> = {
  submitted: "warning",
  triaging: "warning",
  investigating: "warning",
  action_taken: "success",
  rejected: "error",
  closed: "muted",
};

export default function AdminLegalPage() {
  const [items, setItems] = useState<TakedownAdminPublic[]>([]);
  const [total, setTotal] = useState(0);
  const [overdueCount, setOverdueCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [onlyOverdue, setOnlyOverdue] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const response = await listTakedownRequests({
        request_type: typeFilter || undefined,
        status: statusFilter || undefined,
        only_overdue: onlyOverdue,
        limit: 100,
      });
      setItems(response.data);
      setTotal(response.total);
      setOverdueCount(response.overdue_count);
    } catch (err) {
      toast.error((err as ApiException).message || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typeFilter, statusFilter, onlyOverdue]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            Yasal talepler
          </h1>
          <p className="text-sm text-muted-foreground">
            Toplam {total} · SLA aşan {overdueCount}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Yenile
        </Button>
      </div>

      {overdueCount > 0 && (
        <Card className="border-red-200 bg-red-50 dark:bg-red-950/30">
          <CardContent className="flex items-start gap-3 py-3 text-sm">
            <AlertTriangle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-medium text-red-900 dark:text-red-100">
                {overdueCount} talep SLA süresini aştı
              </p>
              <button
                onClick={() => setOnlyOverdue(true)}
                className="text-xs text-red-700 hover:underline"
              >
                Sadece SLA aşanları göster
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="flex flex-wrap items-end gap-4 py-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Tür</label>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Hepsi</option>
              {Object.entries(TYPE_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Durum</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Hepsi</option>
              {Object.entries(STATUS_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm pt-5 cursor-pointer">
            <input
              type="checkbox"
              checked={onlyOverdue}
              onChange={(e) => setOnlyOverdue(e.target.checked)}
            />
            Sadece SLA aşanlar
          </label>
        </CardContent>
      </Card>

      {loading ? (
        <div className="rounded-md border bg-card p-12 text-center text-sm text-muted-foreground">
          Yükleniyor…
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Henüz talep yok</CardTitle>
          </CardHeader>
        </Card>
      ) : (
        <div className="rounded-md border bg-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs font-semibold uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Ticket</th>
                <th className="px-4 py-3">Tür</th>
                <th className="px-4 py-3">Durum</th>
                <th className="px-4 py-3">Talep eden</th>
                <th className="px-4 py-3">SLA</th>
                <th className="px-4 py-3">Tarih</th>
                <th className="px-4 py-3 text-right">İşlem</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr
                  key={t.id}
                  className={`border-t hover:bg-muted/30 transition-colors ${
                    t.overdue ? "bg-red-50/40 dark:bg-red-950/20" : ""
                  }`}
                >
                  <td className="px-4 py-3 font-mono text-xs">{t.ticket_id}</td>
                  <td className="px-4 py-3">
                    <Badge variant="outline">{TYPE_LABEL[t.request_type]}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={STATUS_VARIANT[t.status] ?? "muted"}>
                      {STATUS_LABEL[t.status] ?? t.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-xs">{t.requester_name || t.requester_email}</div>
                    {t.requester_organization && (
                      <div className="text-[10px] text-muted-foreground">
                        {t.requester_organization}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {t.overdue ? (
                      <Badge variant="error">Aştı</Badge>
                    ) : (
                      <span className="text-muted-foreground">
                        {new Date(t.sla_due_at).toLocaleString("tr-TR", {
                          day: "2-digit",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {new Date(t.submitted_at).toLocaleString("tr-TR", {
                      day: "2-digit",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/admin/legal/${t.ticket_id}`}>Detay</Link>
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
