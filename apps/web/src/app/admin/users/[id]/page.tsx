"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Save,
  Trash2,
  RotateCcw,
  CheckCircle2,
  XCircle,
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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/auth-context";
import {
  ApiException,
  getAdminUser,
  restoreAdminUser,
  updateAdminUser,
  type AdminUserDetail,
} from "@/lib/api";

export default function AdminUserDetailPage() {
  const params = useParams<{ id: string }>();
  const userId = params?.id ?? "";
  const { user: currentUser } = useAuth();

  const [u, setU] = useState<AdminUserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [role, setRole] = useState("user");
  const [tier, setTier] = useState("free");
  const [isActive, setIsActive] = useState(true);
  const [note, setNote] = useState("");

  async function load() {
    if (!userId) return;
    setLoading(true);
    try {
      const data = await getAdminUser(userId);
      setU(data);
      setRole(data.role);
      setTier(data.tier);
      setIsActive(data.is_active);
    } catch (err) {
      toast.error((err as ApiException).message || "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const isSelf = currentUser?.id === u?.id;

  async function handleSave() {
    if (!u) return;
    if (isSelf && (role !== u.role || !isActive)) {
      toast.error(
        "Kendi rolünü düşüremez veya hesabını pasif edemezsin (lockout koruma)",
      );
      return;
    }
    setSaving(true);
    try {
      const updated = await updateAdminUser(userId, {
        role: role !== u.role ? role : undefined,
        tier: tier !== u.tier ? tier : undefined,
        is_active: isActive !== u.is_active ? isActive : undefined,
        note: note || undefined,
      });
      setU(updated);
      setNote("");
      toast.success("Güncellendi");
    } catch (err) {
      toast.error((err as ApiException).message || "Güncelleme başarısız");
    } finally {
      setSaving(false);
    }
  }

  async function handleRestore() {
    if (!u) return;
    if (!confirm("Bu hesabı silinmiş listesinden geri yüklemek istediğinden emin misin?"))
      return;
    setSaving(true);
    try {
      const updated = await restoreAdminUser(userId, note || undefined);
      setU(updated);
      setNote("");
      toast.success("Hesap geri yüklendi");
    } catch (err) {
      toast.error((err as ApiException).message || "Geri yükleme başarısız");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="text-sm text-muted-foreground">Yükleniyor…</div>;
  }

  if (!u) {
    return (
      <div className="space-y-4">
        <Button asChild variant="ghost" size="sm">
          <Link href="/admin/users">
            <ArrowLeft className="h-4 w-4" />
            Kullanıcılara dön
          </Link>
        </Button>
        <p>Kullanıcı bulunamadı.</p>
      </div>
    );
  }

  const consentBadge = (ts: string | null) =>
    ts ? (
      <span className="text-xs inline-flex items-center gap-1 text-emerald-700">
        <CheckCircle2 className="h-3 w-3" />
        {new Date(ts).toLocaleDateString("tr-TR")}
      </span>
    ) : (
      <span className="text-xs inline-flex items-center gap-1 text-muted-foreground">
        <XCircle className="h-3 w-3" />
        Onay yok
      </span>
    );

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <Button asChild variant="ghost" size="sm">
          <Link href="/admin/users">
            <ArrowLeft className="h-4 w-4" />
            Kullanıcılara dön
          </Link>
        </Button>
        <div className="flex items-center gap-2">
          {u.deleted_at && <Badge variant="error">Silinmiş</Badge>}
          {isSelf && <Badge variant="warning">Bu sensin</Badge>}
          {u.email_verified && <Badge variant="success">E-posta onaylı</Badge>}
        </div>
      </div>

      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{u.email}</h1>
        {u.full_name && (
          <p className="text-sm text-muted-foreground">{u.full_name}</p>
        )}
        <p className="text-xs text-muted-foreground font-mono mt-1">
          {u.id}
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Hesap</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Rol</span>
              <span>
                {u.role === "super_admin" ? "Süper Admin" : "Kullanıcı"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tier</span>
              <span className="font-mono">{u.tier}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Locale</span>
              <span>{u.locale}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">2FA</span>
              <span>{u.totp_enabled ? "Açık" : "Kapalı"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Son giriş</span>
              <span>
                {u.last_login_at
                  ? new Date(u.last_login_at).toLocaleString("tr-TR")
                  : "Hiç giriş yok"}
              </span>
            </div>
            {u.last_login_ip && (
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">IP</span>
                <span className="font-mono">{u.last_login_ip}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">Kayıt</span>
              <span>{new Date(u.created_at).toLocaleString("tr-TR")}</span>
            </div>
            {u.deleted_at && (
              <div className="flex justify-between text-destructive">
                <span>Silinme</span>
                <span>{new Date(u.deleted_at).toLocaleString("tr-TR")}</span>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">KVKK Onayları</CardTitle>
            <CardDescription>
              Kayıt anında alınan açık rıza zaman damgaları.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Aydınlatma metni</span>
              {consentBadge(u.kvkk_acknowledgment_at)}
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Veri işleme</span>
              {consentBadge(u.data_processing_consent_at)}
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">
                Yurt dışı transfer (m.9)
              </span>
              {consentBadge(u.foreign_transfer_consent_at)}
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Pazarlama</span>
              {consentBadge(u.marketing_consent_at)}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Yönetim */}
      {!u.deleted_at ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Yönetim</CardTitle>
            <CardDescription>
              Role/tier/aktif değişiklikleri admin_audit_log'a yazılır.
              {isSelf && (
                <span className="block mt-1 text-amber-700">
                  ⚠️ Kendi hesabında rol düşüremez veya pasif edemezsin (lockout
                  koruma).
                </span>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="role">Rol</Label>
                <select
                  id="role"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="user">Kullanıcı</option>
                  <option value="super_admin">Süper Admin</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tier">Tier</Label>
                <select
                  id="tier"
                  value={tier}
                  onChange={(e) => setTier(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="trial">Trial</option>
                  <option value="free">Free</option>
                  <option value="starter">Starter</option>
                  <option value="pro">Pro</option>
                  <option value="agency_seat">Agency Seat</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="active">Durum</Label>
                <select
                  id="active"
                  value={isActive ? "active" : "inactive"}
                  onChange={(e) => setIsActive(e.target.value === "active")}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="active">Aktif</option>
                  <option value="inactive">Pasif</option>
                </select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="note">Not (audit log'a yazılır)</Label>
              <Textarea
                id="note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="Değişikliğin gerekçesi (opsiyonel)"
                maxLength={500}
              />
            </div>

            <div className="flex justify-end">
              <Button
                onClick={handleSave}
                disabled={saving}
                variant="accent"
              >
                <Save className="h-4 w-4" />
                {saving ? "Kaydediliyor…" : "Kaydet"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="border-red-200 bg-red-50 dark:bg-red-950/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-red-900 dark:text-red-100">
              <Trash2 className="h-5 w-5" />
              Silinmiş hesap
            </CardTitle>
            <CardDescription className="text-red-800 dark:text-red-200">
              KVKK md.7 kapsamında soft delete. Hard delete 30 gün sonra
              gerçekleşir. Bu süre içinde geri yüklenebilir.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="restore-note">Geri yükleme notu</Label>
              <Textarea
                id="restore-note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="Hesap geri yükleme gerekçesi"
                maxLength={500}
              />
            </div>
            <Button onClick={handleRestore} disabled={saving} variant="outline">
              <RotateCcw className="h-4 w-4" />
              {saving ? "Geri yükleniyor…" : "Hesabı geri yükle"}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
