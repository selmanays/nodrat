"use client";

/**
 * KVKK m.9 yurt dışı transfer açık rıza modal (#453).
 *
 * Backend (#470 PR #492) ile entegre:
 *   - GET  /app/consent/status          — sayfa yüklerken çağırılır
 *   - POST /app/consent/foreign-transfer — checkbox onayı sonrası grant
 *
 * Tetikleme koşulları:
 *   - has_consent = false           → modal force-show (LLM/billing kullanılamaz)
 *   - needs_re_consent = true       → modal banner-style (legacy v0.1 → v0.2 upgrade)
 *
 * Avukat şartlı onayı (Epic #448 §3.9 N-09):
 *   - Checkbox "hizmet koşullarına gömülü değil" — ayrı, açık, loglanabilir
 *   - Server-side enforcement (backend gate); modal UI'ın bypass'ı bile
 *     /app/generate'i 403'e düşürür
 *
 * Reddedildiğinde: /app/generate, billing checkout, email send hepsi 403.
 * Free tier search vs erişim devam eder (sadece yurt dışı çağrı bloklanır).
 */

import { useState } from "react";
import { Globe, Shield, X } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { ApiException } from "@/lib/api";
import {
  grantForeignTransferConsent,
  type ConsentStatus,
} from "@/lib/consent-api";

interface Props {
  status: ConsentStatus;
  open: boolean;
  onClose: () => void;
  onGranted: (newStatus: { consent_at: string; version: string }) => void;
}

export function ForeignTransferConsentModal({
  status,
  open,
  onClose,
  onGranted,
}: Props) {
  const [accepted, setAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const isReConsent = status.needs_re_consent && status.has_consent;

  async function handleSubmit() {
    if (!accepted) {
      toast.error("Devam etmek için açık rıza onayını işaretleyin.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await grantForeignTransferConsent(status.current_version);
      toast.success(
        isReConsent
          ? "Aydınlatma metni güncellendi. Onayınız kaydedildi."
          : "Açık rıza kaydedildi. Tüm özelliklere erişim açık.",
      );
      onGranted({ consent_at: result.consent_at, version: result.version });
      onClose();
    } catch (err) {
      const message =
        err instanceof ApiException
          ? err.message
          : "Bir hata oluştu, lütfen tekrar deneyin.";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o && status.has_consent) {
          // Re-consent durumunda kapatılabilir (kullanıcı sonra onaylayabilir)
          onClose();
        }
        // İlk consent yoksa modal blocking kalır (force-grant flow)
      }}
    >
      <DialogContent
        className="flex max-h-[90dvh] flex-col sm:max-w-lg"
        onPointerDownOutside={(e) => {
          // İlk consent yoksa dış tıklama ile kapatma
          if (!status.has_consent) e.preventDefault();
        }}
        onEscapeKeyDown={(e) => {
          if (!status.has_consent) e.preventDefault();
        }}
      >
        <DialogHeader className="shrink-0">
          <div className="flex items-center gap-2">
            <Shield className="size-5 text-primary" />
            <DialogTitle>
              {isReConsent
                ? "Aydınlatma metni güncellendi"
                : "Yurt dışı veri transferi açık rızası (KVKK m.9)"}
            </DialogTitle>
          </div>
          <DialogDescription className="pt-2">
            {isReConsent
              ? `Sürüm ${status.version || "v0.1"} → ${status.current_version}. Yeni metin için onayınız gerekli.`
              : "Hizmet'i kullanabilmeniz için aşağıdaki bilgilendirmeyi okuyup onaylamanız gerekiyor."}
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto py-2 text-sm">
          <div className="flex items-start gap-3 rounded-lg border bg-muted/30 p-3">
            <Globe className="mt-0.5 size-4 flex-shrink-0 text-muted-foreground" />
            <div className="space-y-2">
              <p className="font-medium">Hangi veriler yurt dışına aktarılır?</p>
              <ul className="ml-4 list-disc space-y-1 text-muted-foreground">
                <li>
                  <strong>Yapay zeka içerik üretimi:</strong> İsteğiniz (prompt) ve
                  gündem kartları PII redaction sonrası DeepSeek (HK) ve Anthropic
                  (ABD) gibi sağlayıcılara iletilir.
                </li>
                <li>
                  <strong>E-posta gönderimi:</strong> Hesap doğrulama, parola
                  sıfırlama, fatura bildirimleri Resend / Postmark (ABD) üzerinden.
                </li>
                <li>
                  <strong>Ödeme + faturalama:</strong> Lemon Squeezy (Merchant of
                  Record, ABD) ödeme bilgilerinizi (ad, e-posta, fatura adresi,
                  ülke, IP, kart token) işler. Kart numarası/CVV bizden geçmez —
                  doğrudan Lemon Squeezy PCI-DSS Level 1 uyumlu ortamda.
                </li>
              </ul>
            </div>
          </div>

          <div className="space-y-1 text-muted-foreground">
            <p>
              <strong className="text-foreground">Hukuki dayanak:</strong>{" "}
              KVKK m.9 — yurt dışına kişisel veri aktarımı ayrı açık rıza
              gerektirir.
            </p>
            <p>
              <strong className="text-foreground">Geri çekme:</strong> KVKK m.11
              uyarınca dilediğiniz zaman /app/me sayfasından açık rızanızı geri
              çekebilirsiniz.
            </p>
            <p>
              <strong className="text-foreground">Reddetme:</strong> Açık rıza
              vermezseniz yapay zeka üretimi, ödeme ve transactional e-posta
              özelliklerine erişemezsiniz; ancak hesabınız ve public arama
              kullanılabilir.
            </p>
          </div>

          <div className="flex items-start gap-2 rounded-lg border-2 border-primary/30 bg-primary/5 p-3">
            <Checkbox
              id="ft-consent"
              checked={accepted}
              onCheckedChange={(checked) => setAccepted(checked === true)}
              className="mt-0.5"
            />
            <Label
              htmlFor="ft-consent"
              className="cursor-pointer text-sm font-normal leading-relaxed"
            >
              <strong>Açık rıza onayı:</strong> Yukarıda belirtilen yurt dışı
              hizmet sağlayıcılarına (DeepSeek, Anthropic, OpenRouter, NVIDIA NIM,
              Resend/Postmark, Lemon Squeezy) kişisel verilerimin aktarılmasına{" "}
              <strong>KVKK m.9 kapsamında açık rızamı</strong> veriyorum. Bu
              rızanın istediğim zaman geri çekilebileceğini biliyorum.
            </Label>
          </div>

          <p className="text-xs text-muted-foreground">
            Detaylı bilgi:{" "}
            <Link
              href="/legal/kvkk-aydinlatma"
              className="underline hover:text-foreground"
              target="_blank"
            >
              KVKK Aydınlatma Metni
            </Link>{" "}
            ·{" "}
            <Link
              href="/legal/privacy"
              className="underline hover:text-foreground"
              target="_blank"
            >
              Gizlilik Politikası
            </Link>
            {" — Sürüm "}
            {status.current_version}
          </p>
        </div>

        <DialogFooter className="shrink-0 flex-col gap-2 sm:flex-row">
          {isReConsent && (
            <Button
              variant="ghost"
              onClick={onClose}
              disabled={submitting}
              className="sm:mr-auto"
            >
              <X className="size-4" />
              Sonra
            </Button>
          )}
          <Button
            onClick={handleSubmit}
            disabled={!accepted || submitting}
            className="w-full sm:w-auto"
          >
            {submitting ? "Kaydediliyor…" : "Açık rıza ver ve devam et"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
