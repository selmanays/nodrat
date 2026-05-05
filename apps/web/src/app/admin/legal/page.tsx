"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/blocks/page-header";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { cn } from "@/lib/utils";
import { formatTrDateTime } from "@/lib/format";
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
  "default" | "secondary" | "destructive" | "outline"
> = {
  submitted: "outline",
  triaging: "outline",
  investigating: "outline",
  action_taken: "secondary",
  rejected: "destructive",
  closed: "secondary",
};

const TABLE_COL_COUNT = 7;

export default function AdminLegalPage() {
  const [items, setItems] = useState<TakedownAdminPublic[]>([]);
  const [total, setTotal] = useState(0);
  const [overdueCount, setOverdueCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [onlyOverdue, setOnlyOverdue] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const response = await listTakedownRequests({
        request_type: typeFilter === "all" ? undefined : typeFilter,
        status: statusFilter === "all" ? undefined : statusFilter,
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
      <PageHeader
        title="Yasal talepler"
        description="Kullanıcı kaldırma talepleri, FSEK telif ve KVKK başvuruları."
      />

      {overdueCount > 0 && !onlyOverdue && (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>{overdueCount} talep SLA süresini aştı</AlertTitle>
          <AlertDescription>
            <button
              type="button"
              onClick={() => setOnlyOverdue(true)}
              className="underline-offset-2 hover:underline"
            >
              Sadece SLA aşanları göster
            </button>
          </AlertDescription>
        </Alert>
      )}

      {/* Filtre satırı — kart dışı */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <Select value={typeFilter} onValueChange={setTypeFilter}>
            <SelectTrigger size="sm" className="w-[180px]">
              <SelectValue placeholder="Tür" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tüm türler</SelectItem>
              {Object.entries(TYPE_LABEL).map(([k, v]) => (
                <SelectItem key={k} value={k}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger size="sm" className="w-[180px]">
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
          <div className="flex items-center gap-2 pl-1">
            <Switch
              id="legal-only-overdue"
              checked={onlyOverdue}
              onCheckedChange={setOnlyOverdue}
            />
            <label
              htmlFor="legal-only-overdue"
              className="text-sm text-muted-foreground"
            >
              Sadece SLA aşanlar
            </label>
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

      {/* Tablo card */}
      <Card className="overflow-hidden rounded-2xl py-0 shadow-none ring-[var(--border)]">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-b bg-muted/50 hover:bg-muted/50">
                  <TableHead className="px-6">Ticket</TableHead>
                  <TableHead>Tür</TableHead>
                  <TableHead>Durum</TableHead>
                  <TableHead>Talep eden</TableHead>
                  <TableHead>SLA</TableHead>
                  <TableHead>Tarih</TableHead>
                  <TableHead className="px-6 text-right">İşlem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 6 }).map((_, i) => (
                    <TableRow key={`skel-${i}`}>
                      <TableCell colSpan={TABLE_COL_COUNT}>
                        <Skeleton className="h-5 w-full" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : items.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={TABLE_COL_COUNT}
                      className="h-32 text-center text-sm text-muted-foreground"
                    >
                      Filtreye uyan talep yok.
                    </TableCell>
                  </TableRow>
                ) : (
                  items.map((t) => (
                    <TableRow
                      key={t.id}
                      className={t.overdue ? "bg-destructive/5" : undefined}
                    >
                      <TableCell className="px-6 font-mono text-xs">
                        {t.ticket_id}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {TYPE_LABEL[t.request_type] ?? t.request_type}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={STATUS_VARIANT[t.status] ?? "outline"}>
                          {STATUS_LABEL[t.status] ?? t.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-medium">
                            {t.requester_name || t.requester_email}
                          </span>
                          {t.requester_organization && (
                            <span className="text-xs text-muted-foreground">
                              {t.requester_organization}
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {t.overdue ? (
                          <Badge variant="destructive">Aştı</Badge>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            {formatTrDateTime(t.sla_due_at)}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatTrDateTime(t.submitted_at)}
                      </TableCell>
                      <TableCell className="px-6 text-right">
                        <Button asChild size="sm" variant="outline">
                          <Link href={`/admin/legal/${t.ticket_id}`}>
                            Detay
                          </Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t px-6 py-3 text-sm">
            <span className="text-muted-foreground">
              {loading ? (
                <Skeleton className="inline-block h-3.5 w-32 align-middle" />
              ) : total === 0 ? (
                "0 talep"
              ) : (
                <>
                  <span className="font-medium tabular-nums text-foreground">
                    {total.toLocaleString("tr-TR")}
                  </span>{" "}
                  talep
                  {overdueCount > 0 && (
                    <>
                      {" · "}
                      <span className="text-destructive">
                        {overdueCount} SLA aştı
                      </span>
                    </>
                  )}
                </>
              )}
            </span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
