"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, Save } from "lucide-react";
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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiException,
  getTakedownRequest,
  updateTakedownRequest,
  type TakedownAdminPublic,
} from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  abuse: "Kötüye kullanım",
  takedown: "5651 Kaldırma",
  copyright: "FSEK Telif",
  privacy_request: "KVKK md.11",
};

const STATUS_OPTIONS = [
  { value: "submitted", label: "Yeni" },
  { value: "triaging", label: "Triajda" },
  { value: "investigating", label: "İnceleniyor" },
  { value: "action_taken", label: "Aksiyon alındı" },
  { value: "rejected", label: "Reddedildi" },
  { value: "closed", label: "Kapalı" },
];

const PRIORITY_OPTIONS = [
  { value: "low", label: "Düşük" },
  { value: "normal", label: "Normal" },
  { value: "high", label: "Yüksek" },
  { value: "critical", label: "Kritik" },
];

export default function TakedownDetailPage() {
  const params = useParams<{ ticket: string }>();
  const ticketId = params?.ticket ?? "";
  const [t, setT] = useState<TakedownAdminPublic | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Editable fields
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [actionTaken, setActionTaken] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [internalNotes, setInternalNotes] = useState("");

  async function load() {
    if (!ticketId) return;
    setLoading(true);
    try {
      const data = await getTakedownRequest(ticketId);
      setT(data);
      setStatus(data.status);
      setPriority(data.priority);
      setActionTaken(data.action_taken || "");
      setRejectionReason(data.rejection_reason || "");
      setInternalNotes(data.internal_notes || "");
    } catch (err) {
      toast.error((err as ApiException).message || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketId]);

  async function handleSave(opts?: { assignSelf?: boolean }) {
    if (!t) return;
    setSaving(true);
    try {
      const updated = await updateTakedownRequest(ticketId, {
        status: status !== t.status ? status : undefined,
        priority: priority !== t.priority ? priority : undefined,
        action_taken:
          actionTaken !== (t.action_taken || "") ? actionTaken : undefined,
        rejection_reason:
          rejectionReason !== (t.rejection_reason || "")
            ? rejectionReason
            : undefined,
        internal_notes:
          internalNotes !== (t.internal_notes || "") ? internalNotes : undefined,
        assign_to_self: opts?.assignSelf,
      });
      setT(updated);
      toast.success("Güncellendi");
    } catch (err) {
      toast.error((err as ApiException).message || "Güncelleme başarısız");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="text-sm text-muted-foreground">Yükleniyor…</div>;
  }

  if (!t) {
    return (
      <div className="space-y-4">
        <Button asChild variant="ghost" size="sm">
          <Link href="/admin/legal">
            <ArrowLeft className="h-4 w-4" />
            Yasal taleplere dön
          </Link>
        </Button>
        <p>Talep bulunamadı.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <Button asChild variant="ghost" size="sm">
          <Link href="/admin/legal">
            <ArrowLeft className="h-4 w-4" />
            Yasal taleplere dön
          </Link>
        </Button>
        <div className="flex items-center gap-2">
          <Badge variant="outline">{TYPE_LABEL[t.request_type]}</Badge>
          {t.overdue && <Badge variant="error">SLA aştı</Badge>}
        </div>
      </div>

      <div>
        <h1 className="text-3xl font-semibold tracking-tight font-mono">
          {t.ticket_id}
        </h1>
        <p className="text-sm text-muted-foreground">
          Gönderildi: {new Date(t.submitted_at).toLocaleString("tr-TR")} · SLA:{" "}
          {new Date(t.sla_due_at).toLocaleString("tr-TR")}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Talep eden</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 md:grid-cols-2 text-sm">
          <div>
            <span className="text-muted-foreground">İsim:</span>{" "}
            {t.requester_name || "—"}
          </div>
          <div>
            <span className="text-muted-foreground">E-posta:</span>{" "}
            <a href={`mailto:${t.requester_email}`} className="text-brand-700 hover:underline">
              {t.requester_email}
            </a>
          </div>
          <div>
            <span className="text-muted-foreground">Telefon:</span>{" "}
            {t.requester_phone || "—"}
          </div>
          <div>
            <span className="text-muted-foreground">Kurum:</span>{" "}
            {t.requester_organization || "—"}
          </div>
          {t.authority_claim && (
            <div className="md:col-span-2">
              <span className="text-muted-foreground">Sıfat:</span>{" "}
              {t.authority_claim}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Şikayet</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {t.subject_url && (
            <p>
              <span className="text-muted-foreground">Konu URL:</span>{" "}
              <a
                href={t.subject_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-700 hover:underline inline-flex items-center gap-1"
              >
                {t.subject_url}
                <ExternalLink className="h-3 w-3" />
              </a>
            </p>
          )}
          <div>
            <p className="text-muted-foreground mb-1">Açıklama:</p>
            <p className="whitespace-pre-wrap rounded-md bg-muted/40 p-3">
              {t.description}
            </p>
          </div>
          {t.evidence_urls.length > 0 && (
            <div>
              <p className="text-muted-foreground mb-1">Kanıt URL'leri:</p>
              <ul className="space-y-1">
                {t.evidence_urls.map((u, i) => (
                  <li key={i}>
                    <a
                      href={u}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-brand-700 hover:underline text-xs inline-flex items-center gap-1"
                    >
                      {u}
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Yönetim</CardTitle>
          <CardDescription>
            Status değişikliği audit log'a yazılır.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="status">Durum</Label>
              <select
                id="status"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                {STATUS_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="priority">Öncelik</Label>
              <select
                id="priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                {PRIORITY_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="action">Alınan aksiyon</Label>
            <Textarea
              id="action"
              value={actionTaken}
              onChange={(e) => setActionTaken(e.target.value)}
              rows={3}
              placeholder="Örn: İçerik kaldırıldı, kaynak güncellendi, vb."
              maxLength={2000}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="reject">Reddetme gerekçesi</Label>
            <Textarea
              id="reject"
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              rows={2}
              placeholder="Talep reddedildiyse gerekçe (talep edene gönderilebilir)"
              maxLength={2000}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="notes">İç notlar (talep eden görmez)</Label>
            <Textarea
              id="notes"
              value={internalNotes}
              onChange={(e) => setInternalNotes(e.target.value)}
              rows={3}
              maxLength={5000}
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => handleSave()} disabled={saving} variant="accent">
              <Save className="h-4 w-4" />
              {saving ? "Kaydediliyor…" : "Kaydet"}
            </Button>
            {!t.assigned_to && (
              <Button
                variant="outline"
                onClick={() => handleSave({ assignSelf: true })}
                disabled={saving}
              >
                Bana ata
              </Button>
            )}
            {t.assigned_to && (
              <span className="text-xs text-muted-foreground">
                Atanan: {t.assigned_to.slice(0, 8)}…
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Zaman çizelgesi</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-xs">
          <div>
            <span className="text-muted-foreground">Submitted:</span>{" "}
            {new Date(t.submitted_at).toLocaleString("tr-TR")}
          </div>
          {t.triaged_at && (
            <div>
              <span className="text-muted-foreground">Triajlandı:</span>{" "}
              {new Date(t.triaged_at).toLocaleString("tr-TR")}
            </div>
          )}
          {t.investigating_at && (
            <div>
              <span className="text-muted-foreground">İncelemeye alındı:</span>{" "}
              {new Date(t.investigating_at).toLocaleString("tr-TR")}
            </div>
          )}
          {t.resolved_at && (
            <div>
              <span className="text-muted-foreground">Sonuçlandı:</span>{" "}
              {new Date(t.resolved_at).toLocaleString("tr-TR")}
            </div>
          )}
          <div>
            <span className="text-muted-foreground">SLA bitiş:</span>{" "}
            {new Date(t.sla_due_at).toLocaleString("tr-TR")}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
