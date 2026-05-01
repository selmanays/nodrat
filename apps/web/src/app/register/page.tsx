"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/brand/logo";
import { useAuth } from "@/lib/auth-context";
import { ApiException } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const { signUp } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // 4 KVKK consents (3 zorunlu + 1 opsiyonel) + 18+ gate
  const [age18Plus, setAge18Plus] = useState(false);
  const [kvkkAck, setKvkkAck] = useState(false);
  const [dataConsent, setDataConsent] = useState(false);
  const [foreignTransfer, setForeignTransfer] = useState(false);
  const [marketing, setMarketing] = useState(false);

  const allMandatoryAccepted =
    age18Plus && kvkkAck && dataConsent && foreignTransfer;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (password.length < 12) {
      toast.error("Şifre en az 12 karakter olmalı");
      return;
    }
    if (!allMandatoryAccepted) {
      toast.error("Zorunlu onayların hepsi işaretlenmelidir");
      return;
    }

    setSubmitting(true);
    try {
      await signUp({
        email,
        password,
        full_name: fullName || null,
        kvkk_acknowledgment: kvkkAck,
        data_processing_consent: dataConsent,
        foreign_transfer_consent: foreignTransfer,
        marketing_consent: marketing,
        age_18_plus: age18Plus,
      });
      toast.success("Hesabın oluşturuldu — hoş geldin");
      router.replace("/app/generate");
    } catch (error) {
      const apiError = error as ApiException;
      toast.error(apiError.message || "Kayıt başarısız");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-brand-50 p-4 py-8 dark:bg-brand-950">
      <Card className="w-full max-w-2xl">
        <CardHeader className="space-y-3">
          <Link href="/" aria-label="Nodrat anasayfasına dön" className="inline-flex">
            <Logo variant="wordmark" size="md" />
          </Link>
          <CardTitle className="text-2xl">Hesap oluştur</CardTitle>
          <CardDescription>
            Türkçe gündemden kaynaklı X içerikleri üret. ChatGPT yanında, gündem için özel araç.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Temel bilgiler */}
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="email">E-posta *</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="ornek@nodrat.com"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="full_name">Ad Soyad</Label>
                <Input
                  id="full_name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  maxLength={120}
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="password">Şifre * (en az 12 karakter)</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={12}
                  maxLength={128}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </div>

            {/* 18+ gate */}
            <div className="rounded-md border-2 border-amber-200 bg-amber-50 p-3 dark:bg-amber-950/30">
              <div className="flex items-start gap-3">
                <Checkbox
                  id="age_18_plus"
                  checked={age18Plus}
                  onCheckedChange={setAge18Plus}
                  className="mt-0.5"
                />
                <div className="space-y-0.5">
                  <Label htmlFor="age_18_plus" className="font-medium cursor-pointer">
                    18 yaşından büyüğüm * (Zorunlu)
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Nodrat içeriği yetişkinlere yöneliktir. KVKK m.6'ya göre
                    küçükler için ayrı onay gerekir; bu hizmet 18+ kullanıcılara açıktır.
                  </p>
                </div>
              </div>
            </div>

            {/* 4 KVKK checkboxes */}
            <div className="space-y-3">
              <h3 className="text-sm font-semibold">KVKK Onayları</h3>

              <div className="rounded-md border p-3">
                <div className="flex items-start gap-3">
                  <Checkbox
                    id="kvkk_ack"
                    checked={kvkkAck}
                    onCheckedChange={setKvkkAck}
                    className="mt-0.5"
                  />
                  <div className="space-y-0.5">
                    <Label htmlFor="kvkk_ack" className="font-medium cursor-pointer">
                      KVKK Aydınlatma Metni'ni okudum * (Zorunlu)
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      <Link
                        href="/legal/kvkk-aydinlatma"
                        target="_blank"
                        className="text-brand-700 hover:underline"
                      >
                        Aydınlatma metnini oku
                      </Link>
                    </p>
                  </div>
                </div>
              </div>

              <div className="rounded-md border p-3">
                <div className="flex items-start gap-3">
                  <Checkbox
                    id="data_consent"
                    checked={dataConsent}
                    onCheckedChange={setDataConsent}
                    className="mt-0.5"
                  />
                  <div className="space-y-0.5">
                    <Label htmlFor="data_consent" className="font-medium cursor-pointer">
                      Kişisel verilerin işlenmesine onay * (Zorunlu)
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      Hesap oluşturma, kullanım istatistikleri, fatura ve destek için.
                    </p>
                  </div>
                </div>
              </div>

              <div className="rounded-md border p-3">
                <div className="flex items-start gap-3">
                  <Checkbox
                    id="foreign_transfer"
                    checked={foreignTransfer}
                    onCheckedChange={setForeignTransfer}
                    className="mt-0.5"
                  />
                  <div className="space-y-0.5">
                    <Label htmlFor="foreign_transfer" className="font-medium cursor-pointer">
                      Yurt dışı LLM provider'larına aktarım onayı * (Zorunlu)
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      İçerik üretimi için DeepSeek (NVIDIA NIM), Anthropic gibi yurt dışı
                      provider'lara, KVKK m.9 kapsamında PII redact edilmiş veriler gider.
                    </p>
                  </div>
                </div>
              </div>

              <div className="rounded-md border p-3">
                <div className="flex items-start gap-3">
                  <Checkbox
                    id="marketing"
                    checked={marketing}
                    onCheckedChange={setMarketing}
                    className="mt-0.5"
                  />
                  <div className="space-y-0.5">
                    <Label htmlFor="marketing" className="font-medium cursor-pointer">
                      Pazarlama iletisi (opsiyonel)
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      Yeni özellikler, kampanyalar için mail. Tek tıkla abonelikten çık.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={submitting || !allMandatoryAccepted}
            >
              {submitting ? "Hesap oluşturuluyor…" : "Hesabı oluştur"}
            </Button>
          </form>
        </CardContent>
        <CardContent className="border-t pt-4 text-sm text-muted-foreground">
          Zaten hesabın var mı?{" "}
          <Link href="/login" className="font-medium text-brand-700 hover:underline">
            Giriş yap
          </Link>
        </CardContent>
      </Card>
    </main>
  );
}
