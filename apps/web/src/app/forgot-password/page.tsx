"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Mail } from "lucide-react";

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
import { Logo } from "@/components/brand/logo";
import { ApiException, apiFetch } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch<{ ok: boolean; detail: string | null }>(
        "/auth/password-reset-request",
        {
          method: "POST",
          body: { email },
          skipAuth: true,
        },
      );
      setSubmitted(true);
    } catch (err) {
      // Email enumeration koruması: backend zaten silent OK döner.
      // Bu catch sadece network/server error içindir.
      const apiError = err as ApiException;
      setError(apiError.message || "İşlem başarısız. Lütfen tekrar dene.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-md rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader className="space-y-3">
          <Link href="/" aria-label="Nodrat anasayfasına dön" className="inline-flex">
            <Logo variant="wordmark" size="md" />
          </Link>
          <CardTitle className="text-2xl">Şifremi unuttum</CardTitle>
          <CardDescription>
            Kayıtlı e-posta adresine bir sıfırlama bağlantısı göndereceğiz.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {submitted ? (
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <Mail className="h-10 w-10 text-primary" />
              <CardTitle className="text-base">E-posta gönderildi</CardTitle>
              <CardDescription>
                Hesap kayıtlıysa <strong>{email}</strong> adresine bir sıfırlama
                bağlantısı gönderdik. Gelen kutunu (ve gerekirse spam klasörünü)
                kontrol et. Bağlantı 1 saat içinde geçerli.
              </CardDescription>
              <Link href="/login" className="mt-4 w-full">
                <Button variant="outline" className="w-full">
                  Giriş sayfasına dön
                </Button>
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">E-posta</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="ornek@nodrat.com"
                  disabled={submitting}
                />
              </div>
              {error && (
                <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
              )}
              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting ? "Gönderiliyor…" : "Sıfırlama bağlantısı gönder"}
              </Button>
            </form>
          )}
        </CardContent>
        <CardContent className="border-t pt-4 text-sm text-muted-foreground">
          Şifreni hatırladın mı?{" "}
          <Link href="/login" className="font-medium text-primary hover:underline">
            Giriş yap
          </Link>
        </CardContent>
      </Card>
    </main>
  );
}
