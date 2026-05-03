"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Loader2,
  Trash2,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth-context";
import {
  ApiException,
  deleteMe,
  exportMe,
  getMe,
  updateMe,
  type UserMePublic,
} from "@/lib/api";

export default function ProfilePage() {
  const router = useRouter();
  const { signOut } = useAuth();

  const [me, setMe] = useState<UserMePublic | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);

  // Profil form state
  const [fullName, setFullName] = useState("");
  const [locale, setLocale] = useState("tr-TR");
  const [marketingConsent, setMarketingConsent] = useState(false);

  // Hesap silme onayı
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleteReason, setDeleteReason] = useState("");

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      const user = await getMe();
      setMe(user);
      setFullName(user.full_name || "");
      setLocale(user.locale);
      setMarketingConsent(user.marketing_consent_at !== null);
    } catch (err) {
      toast.error((err as ApiException).message || "Profil yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!me) return;
    setSavingProfile(true);
    try {
      const updated = await updateMe({
        full_name: fullName.trim() || null,
        locale,
        marketing_consent: marketingConsent,
      });
      setMe(updated);
      toast.success("Profil güncellendi");
    } catch (err) {
      toast.error((err as ApiException).message || "Güncelleme başarısız");
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      const data = await exportMe();
      // Browser'da indirme tetikle
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `nodrat-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success("Verilerin indiriliyor (KVKK md.11 taşınabilirlik)");
    } catch (err) {
      toast.error((err as ApiException).message || "Export başarısız");
    } finally {
      setExporting(false);
    }
  }

  async function handleDelete() {
    if (deleteConfirmation !== "SIL" && deleteConfirmation !== "DELETE") {
      toast.error("Lütfen 'SIL' veya 'DELETE' yazın");
      return;
    }
    setDeleting(true);
    try {
      await deleteMe(deleteConfirmation, deleteReason || undefined);
      toast.success("Hesap silme talebin alındı. 30 gün içinde tamamlanacak.");
      // Sign out + anasayfaya yönlendir
      await signOut();
      router.replace("/");
    } catch (err) {
      toast.error((err as ApiException).message || "Silme başarısız");
      setDeleting(false);
    }
  }

  if (loading || !me) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  function fmtDate(iso: string | null): string {
    if (!iso) return "—";
    return new Date(iso).toLocaleString("tr-TR", {
      day: "2-digit",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Hesabım</h1>
        <p className="text-sm text-muted-foreground">
          Profil bilgilerin, KVKK hakların ve hesap işlemleri.
        </p>
      </div>

      {/* Email verify uyarısı */}
      {!me.email_verified && (
        <Card className="border-amber-200 bg-amber-50 dark:bg-amber-950/30">
          <CardContent className="flex items-start gap-3 py-3 text-sm">
            <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-medium text-amber-900 dark:text-amber-100">
                E-posta adresin doğrulanmadı
              </p>
              <p className="text-xs text-muted-foreground">
                Üretim yapamazsın. Gelen kutunu kontrol et veya yeni doğrulama
                maili talep et.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Hesap özeti */}
      <Card>
        <CardHeader>
          <CardTitle>Hesap özeti</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">E-posta</span>
            <span className="font-medium">{me.email}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-muted-foreground">E-posta doğrulama</span>
            {me.email_verified ? (
              <Badge variant="secondary">
                <CheckCircle2 className="h-3 w-3" /> Doğrulandı
              </Badge>
            ) : (
              <Badge variant="outline">
                <XCircle className="h-3 w-3" /> Bekliyor
              </Badge>
            )}
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Plan / Tier</span>
            <Badge variant="outline" className="font-mono">{me.tier}</Badge>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Rol</span>
            <Badge variant="outline" className="font-mono">{me.role}</Badge>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Üyelik tarihi</span>
            <span>{fmtDate(me.created_at)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Son giriş</span>
            <span>{fmtDate(me.last_login_at)}</span>
          </div>
        </CardContent>
      </Card>

      {/* Profil düzenleme */}
      <Card>
        <CardHeader>
          <CardTitle>Profil bilgileri</CardTitle>
          <CardDescription>
            E-posta, rol ve plan değişiklikleri için destek ile iletişime geç.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSaveProfile} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="full_name">Ad Soyad</Label>
              <Input
                id="full_name"
                type="text"
                maxLength={120}
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                disabled={savingProfile}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="locale">Dil</Label>
              <select
                id="locale"
                value={locale}
                onChange={(e) => setLocale(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-1.5 text-sm"
                disabled={savingProfile}
              >
                <option value="tr-TR">Türkçe (tr-TR)</option>
                <option value="en-US">English (en-US)</option>
              </select>
            </div>
            <label className="flex items-start gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={marketingConsent}
                onChange={(e) => setMarketingConsent(e.target.checked)}
                disabled={savingProfile}
                className="mt-1"
              />
              <span>
                <span className="font-medium">Pazarlama iletilerine onay</span>
                <span className="block text-xs text-muted-foreground mt-0.5">
                  Yeni özellikler, ipuçları ve duyurular için e-posta almak
                  istiyorum (opsiyonel, istediğin zaman geri alabilirsin).
                </span>
              </span>
            </label>
            <Button type="submit" disabled={savingProfile}>
              {savingProfile ? "Kaydediliyor…" : "Kaydet"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* KVKK consent zaman damgaları */}
      <Card>
        <CardHeader>
          <CardTitle>KVKK onay kayıtların</CardTitle>
          <CardDescription>
            Kayıt sırasında verdiğin onayların zaman damgaları (KVKK md.11).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Aydınlatma metni</span>
            <span>{fmtDate(me.kvkk_acknowledgment_at)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Veri işleme onayı</span>
            <span>{fmtDate(me.data_processing_consent_at)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Yurt dışı aktarım onayı</span>
            <span>{fmtDate(me.foreign_transfer_consent_at)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Pazarlama onayı</span>
            <span>{fmtDate(me.marketing_consent_at)}</span>
          </div>
        </CardContent>
      </Card>

      {/* Veri export (KVKK md.11/e taşınabilirlik) */}
      <Card>
        <CardHeader>
          <CardTitle>Verilerimi indir</CardTitle>
          <CardDescription>
            KVKK md.11 (e bendi) — yapısal formatta veri taşınabilirliği.
            Profil + son 100 üretim + saved + usage events.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="outline"
            onClick={() => void handleExport()}
            disabled={exporting}
          >
            <Download className="h-4 w-4" />
            {exporting ? "Hazırlanıyor…" : "JSON olarak indir"}
          </Button>
        </CardContent>
      </Card>

      {/* Hesap silme — KVKK md.7 + md.11 */}
      <Card className="border-red-200 dark:border-red-900">
        <CardHeader>
          <CardTitle className="text-red-700 dark:text-red-400">
            Hesabı sil
          </CardTitle>
          <CardDescription>
            KVKK md.7 (silme hakkı): Hesabın 30 gün soft-delete sonrası kalıcı
            olarak silinir. Bu süre içinde geri dönüş için support@nodrat.com'a
            yaz.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {!showDeleteConfirm ? (
            <Button
              variant="outline"
              className="border-red-300 text-red-700 hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-950/50"
              onClick={() => setShowDeleteConfirm(true)}
            >
              <Trash2 className="h-4 w-4" />
              Hesabımı silmek istiyorum
            </Button>
          ) : (
            <div className="space-y-3 rounded-md border border-red-300 bg-red-50/50 p-4 dark:border-red-900 dark:bg-red-950/20">
              <p className="text-sm text-red-900 dark:text-red-200">
                <strong>Onay gerekiyor.</strong> Aşağıdaki kutuya{" "}
                <strong>SIL</strong> yazarak işlemi onayla.
              </p>
              <div className="space-y-2">
                <Label htmlFor="delete_confirmation">Onay</Label>
                <Input
                  id="delete_confirmation"
                  type="text"
                  value={deleteConfirmation}
                  onChange={(e) => setDeleteConfirmation(e.target.value)}
                  placeholder="SIL"
                  disabled={deleting}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="delete_reason">
                  Sebep (opsiyonel — bize geri bildirim)
                </Label>
                <Input
                  id="delete_reason"
                  type="text"
                  maxLength={500}
                  value={deleteReason}
                  onChange={(e) => setDeleteReason(e.target.value)}
                  placeholder="örn. ihtiyaç duymuyorum"
                  disabled={deleting}
                />
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="border-red-300 text-red-700 hover:bg-red-100"
                  onClick={() => void handleDelete()}
                  disabled={
                    deleting ||
                    (deleteConfirmation !== "SIL" &&
                      deleteConfirmation !== "DELETE")
                  }
                >
                  {deleting ? "Siliniyor…" : "Hesabı sil"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowDeleteConfirm(false);
                    setDeleteConfirmation("");
                    setDeleteReason("");
                  }}
                  disabled={deleting}
                >
                  İptal
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
