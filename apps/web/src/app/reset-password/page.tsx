"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { toast } from "sonner";

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

function ResetPasswordContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) {
      setTokenError(
        "Sıfırlama bağlantısı eksik. E-postandaki tam bağlantıyı kullan.",
      );
    }
  }, [token]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    if (newPassword !== confirmPassword) {
      toast.error("Şifreler eşleşmiyor");
      return;
    }
    if (newPassword.length < 12) {
      toast.error("Şifre en az 12 karakter olmalı");
      return;
    }
    setSubmitting(true);
    try {
      await apiFetch<{ ok: boolean; detail: string | null }>(
        "/auth/password-reset",
        {
          method: "POST",
          body: { token, new_password: newPassword },
          skipAuth: true,
        },
      );
      setSuccess(true);
      toast.success("Şifren güncellendi");
      setTimeout(() => router.replace("/login"), 3000);
    } catch (err) {
      const apiError = err as ApiException;
      toast.error(apiError.message || "Sıfırlama başarısız");
      setTokenError(
        apiError.message ||
          "Bağlantı geçersiz veya süresi dolmuş. Yeni bir sıfırlama talebi oluştur.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <div className="flex flex-col items-center gap-3 py-6 text-center">
        <CheckCircle2 className="h-12 w-12 text-emerald-500" />
        <CardTitle className="text-lg">Şifren güncellendi</CardTitle>
        <CardDescription>
          Birkaç saniye içinde giriş sayfasına yönlendirileceksin.
        </CardDescription>
      </div>
    );
  }

  if (tokenError) {
    return (
      <div className="flex flex-col items-center gap-3 py-6 text-center">
        <XCircle className="h-12 w-12 text-red-500" />
        <CardTitle className="text-lg">Bağlantı geçersiz</CardTitle>
        <CardDescription>{tokenError}</CardDescription>
        <Link href="/forgot-password" className="mt-4 w-full">
          <Button className="w-full">Yeni sıfırlama talebi</Button>
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="new_password">Yeni şifre</Label>
        <Input
          id="new_password"
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          disabled={submitting}
        />
        <p className="text-xs text-muted-foreground">En az 12 karakter.</p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="confirm_password">Şifreyi onayla</Label>
        <Input
          id="confirm_password"
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          disabled={submitting}
        />
      </div>
      <Button type="submit" className="w-full" disabled={submitting}>
        {submitting ? "Güncelleniyor…" : "Şifreyi güncelle"}
      </Button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-brand-50 p-4 dark:bg-brand-950">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-3">
          <Link href="/" aria-label="Nodrat anasayfasına dön" className="inline-flex">
            <Logo variant="wordmark" size="md" />
          </Link>
          <CardTitle className="text-2xl">Yeni şifre belirle</CardTitle>
        </CardHeader>
        <CardContent>
          <Suspense
            fallback={
              <div className="flex flex-col items-center gap-3 py-8 text-center">
                <Loader2 className="h-8 w-8 animate-spin text-brand-700" />
                <p className="text-sm text-muted-foreground">Yükleniyor…</p>
              </div>
            }
          >
            <ResetPasswordContent />
          </Suspense>
        </CardContent>
      </Card>
    </main>
  );
}
