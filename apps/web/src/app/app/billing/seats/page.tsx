"use client";

/**
 * /app/billing/seats — Agency multi-seat yönetimi (#450, #53 backend).
 *
 * - Mevcut seat sayısı (sub.seat_count) + dolu/boş slotlar
 * - "Davet et" formu (email + role: admin/editor)
 * - Mevcut seat listesi (kabul/davetli durumu, çıkar)
 * - Kabul edilmemiş davet için invite_url copy butonu
 *
 * Non-Agency kullanıcı 404 NO_AGENCY_SUBSCRIPTION → "Agency planına geç" CTA.
 * LS hesap konfigüre değilse (Agency abonelik mümkün değil) → 503 ekrana basılır.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Copy,
  Loader2,
  Mail,
  Trash2,
  UserPlus,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { ApiException } from "@/lib/api";
import {
  inviteSeat,
  isBillingNotConfigured,
  isNoAgencySubscription,
  listSeats,
  removeSeat,
  type SeatItem,
  type SeatsListResponse,
} from "@/lib/billing-api";
import { formatTrDate } from "@/lib/format";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; data: SeatsListResponse }
  | { kind: "no-agency" }
  | { kind: "not-configured"; message: string }
  | { kind: "error"; message: string };

export default function SeatsPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"admin" | "editor">("editor");
  const [inviting, setInviting] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [lastInvite, setLastInvite] = useState<{
    email: string;
    url: string;
  } | null>(null);

  async function load() {
    setState({ kind: "loading" });
    try {
      const data = await listSeats();
      setState({ kind: "ready", data });
    } catch (err) {
      if (isBillingNotConfigured(err)) {
        setState({
          kind: "not-configured",
          message:
            (err as ApiException).message ||
            "Ücretli abonelik sistemi henüz aktif değil.",
        });
        return;
      }
      if (isNoAgencySubscription(err)) {
        setState({ kind: "no-agency" });
        return;
      }
      setState({
        kind: "error",
        message: (err as ApiException).message || "Yüklenemedi",
      });
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      const res = await inviteSeat(inviteEmail.trim(), inviteRole);
      setLastInvite({ email: res.invited_email, url: res.invite_url });
      setInviteEmail("");
      toast.success(`${res.invited_email} davet edildi`);
      await load();
    } catch (err) {
      toast.error((err as ApiException).message || "Davet başarısız");
    } finally {
      setInviting(false);
    }
  }

  async function handleRemove(seat: SeatItem) {
    const confirmed = window.confirm(
      `${seat.invited_email} hesabının koltuğu silinsin mi?`,
    );
    if (!confirmed) return;
    setRemovingId(seat.id);
    try {
      await removeSeat(seat.id);
      toast.success(`${seat.invited_email} çıkarıldı`);
      await load();
    } catch (err) {
      toast.error((err as ApiException).message || "Silinemedi");
    } finally {
      setRemovingId(null);
    }
  }

  async function copyInvite(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Davet bağlantısı kopyalandı");
    } catch {
      toast.error("Kopyalanamadı; bağlantıyı manuel seçin");
    }
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
      <div>
        <Button variant="ghost" size="sm" asChild className="-ml-3 mb-2">
          <Link href="/app/billing">
            <ArrowLeft className="mr-1 size-4" />
            Faturalandırma
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold tracking-tight">
          Ajans koltukları
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Agency planınızdaki koltukları yönetin: takım üyelerini davet edin,
          rolleri belirleyin, ihtiyaç duyduğunuzda çıkarın.
        </p>
      </div>

      {state.kind === "loading" && (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}

      {state.kind === "no-agency" && (
        <Card>
          <CardHeader>
            <CardTitle>Agency planı gerekiyor</CardTitle>
            <CardDescription>
              Multi-seat yönetimi yalnızca Agency tier'da mevcuttur. Şu anki
              planınızdan Agency planına geçerek ekibinize koltuk
              ekleyebilirsiniz.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link href="/app/billing">Planları görüntüle</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {state.kind === "not-configured" && (
        <Card className="border-amber-500/40 bg-amber-50/40 dark:bg-amber-950/20">
          <CardHeader>
            <CardTitle>Yakında aktif</CardTitle>
            <CardDescription>{state.message}</CardDescription>
          </CardHeader>
        </Card>
      )}

      {state.kind === "error" && (
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle>Hata</CardTitle>
            <CardDescription>{state.message}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => void load()}>Tekrar dene</Button>
          </CardContent>
        </Card>
      )}

      {state.kind === "ready" && (
        <SeatsContent
          data={state.data}
          inviteEmail={inviteEmail}
          setInviteEmail={setInviteEmail}
          inviteRole={inviteRole}
          setInviteRole={setInviteRole}
          inviting={inviting}
          onInvite={handleInvite}
          removingId={removingId}
          onRemove={handleRemove}
          lastInvite={lastInvite}
          onCopyInvite={copyInvite}
        />
      )}
    </div>
  );
}

interface SeatsContentProps {
  data: SeatsListResponse;
  inviteEmail: string;
  setInviteEmail: (v: string) => void;
  inviteRole: "admin" | "editor";
  setInviteRole: (v: "admin" | "editor") => void;
  inviting: boolean;
  onInvite: (e: React.FormEvent) => void;
  removingId: string | null;
  onRemove: (seat: SeatItem) => void;
  lastInvite: { email: string; url: string } | null;
  onCopyInvite: (url: string) => void;
}

function SeatsContent({
  data,
  inviteEmail,
  setInviteEmail,
  inviteRole,
  setInviteRole,
  inviting,
  onInvite,
  removingId,
  onRemove,
  lastInvite,
  onCopyInvite,
}: SeatsContentProps) {
  const used = data.seats.length;
  const available = data.seat_count - used;
  const full = available <= 0;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Koltuk durumu</CardTitle>
          <CardDescription>
            <span className="font-medium text-foreground">{data.plan_code}</span>
            {" — "}
            {used} / {data.seat_count} koltuk dolu
            {full ? (
              <span className="ml-2 inline-flex">
                <Badge variant="destructive">Dolu</Badge>
              </span>
            ) : (
              <span className="ml-2 inline-flex">
                <Badge variant="outline">{available} boş</Badge>
              </span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={onInvite}
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
          >
            <div className="flex-1">
              <Label htmlFor="invite-email" className="text-xs">
                Davet edilecek e-posta
              </Label>
              <Input
                id="invite-email"
                type="email"
                placeholder="ornek@sirket.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                disabled={inviting || full}
                required
              />
            </div>
            <div className="w-full sm:w-40">
              <Label htmlFor="invite-role" className="text-xs">
                Rol
              </Label>
              <Select
                value={inviteRole}
                onValueChange={(v) =>
                  setInviteRole(v as "admin" | "editor")
                }
                disabled={inviting || full}
              >
                <SelectTrigger id="invite-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="editor">Editör</SelectItem>
                  <SelectItem value="admin">Yönetici</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button type="submit" disabled={inviting || full}>
              {inviting ? (
                <Loader2 className="mr-1 size-4 animate-spin" />
              ) : (
                <UserPlus className="mr-1 size-4" />
              )}
              Davet et
            </Button>
          </form>
          {full && (
            <p className="mt-3 text-xs text-muted-foreground">
              Tüm koltuklar dolu. Yeni koltuk eklemek için{" "}
              <Link
                href="/app/billing/manage"
                className="underline hover:text-foreground"
              >
                planı yükseltin
              </Link>
              .
            </p>
          )}
        </CardContent>
      </Card>

      {lastInvite && (
        <Card className="border-emerald-500/40 bg-emerald-50/40 dark:bg-emerald-950/20">
          <CardHeader>
            <CardTitle className="text-base">
              Davet gönderildi: {lastInvite.email}
            </CardTitle>
            <CardDescription>
              Davet bağlantısını kopyalayıp manuel paylaşabilirsiniz. (E-posta
              gönderim entegrasyonu yakında.)
            </CardDescription>
          </CardHeader>
          <CardContent className="flex items-center gap-2">
            <Input
              value={lastInvite.url}
              readOnly
              className="font-mono text-xs"
              onFocus={(e) => e.currentTarget.select()}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => onCopyInvite(lastInvite.url)}
            >
              <Copy className="mr-1 size-3" />
              Kopyala
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Koltuk listesi</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {data.seats.length === 0 ? (
            <div className="flex flex-col items-center gap-2 p-8 text-center">
              <Mail className="size-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                Henüz davet edilmiş koltuk yok.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>E-posta</TableHead>
                  <TableHead className="w-[100px]">Rol</TableHead>
                  <TableHead className="w-[120px]">Durum</TableHead>
                  <TableHead className="w-[160px]">Kabul tarihi</TableHead>
                  <TableHead className="w-[100px] text-right">İşlem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.seats.map((seat) => (
                  <TableRow key={seat.id}>
                    <TableCell className="font-medium">
                      {seat.invited_email}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {seat.role === "admin" ? "Yönetici" : "Editör"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {seat.accepted_at ? (
                        <Badge className="bg-emerald-600 hover:bg-emerald-600">
                          Aktif
                        </Badge>
                      ) : (
                        <Badge variant="secondary">Beklemede</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {seat.accepted_at
                        ? formatTrDate(seat.accepted_at)
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={removingId === seat.id}
                        onClick={() => onRemove(seat)}
                      >
                        {removingId === seat.id ? (
                          <Loader2 className="size-4 animate-spin" />
                        ) : (
                          <Trash2 className="size-4 text-destructive" />
                        )}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
