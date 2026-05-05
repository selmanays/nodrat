"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { AlertTriangle, Mail } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { useAuth } from "@/lib/auth-context";
import { ApiException, requestVerifyResend } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [needsVerify, setNeedsVerify] = useState(false);
  const [resendingVerify, setResendingVerify] = useState(false);
  const [verifySent, setVerifySent] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setNeedsVerify(false);
    setVerifySent(false);
    try {
      const user = await signIn({ email, password });
      toast.success("Hoş geldin");
      // super_admin → admin paneli, normal kullanıcı → /app
      router.replace(user.role === "super_admin" ? "/admin/sources" : "/app/generate");
    } catch (error) {
      const apiError = error as ApiException;
      // EMAIL_NOT_VERIFIED için özel UX (toast yerine inline alert)
      if (apiError.code === "EMAIL_NOT_VERIFIED") {
        setNeedsVerify(true);
      } else {
        toast.error(apiError.message || "Giriş başarısız");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResendVerify() {
    if (!email) return;
    setResendingVerify(true);
    try {
      await requestVerifyResend(email);
      setVerifySent(true);
      toast.success("Doğrulama maili gönderildi");
    } catch (err) {
      toast.error((err as ApiException).message || "Gönderim başarısız");
    } finally {
      setResendingVerify(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-md rounded-2xl shadow-none ring-[var(--border)]">
        <CardHeader className="space-y-3">
          <Link href="/" aria-label="Nodrat anasayfasına dön" className="inline-flex">
            <Logo variant="wordmark" size="md" />
          </Link>
          <CardTitle className="text-2xl">Giriş yap</CardTitle>
          <CardDescription>
            Türkçe gündem için editör odaklı üretim aracı.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {needsVerify && (
            <Alert className="mb-4">
              <AlertTriangle />
              <AlertTitle>E-posta doğrulanmamış</AlertTitle>
              <AlertDescription>
                <span>
                  Hesabını kullanmak için <strong>{email}</strong> adresine
                  gönderdiğimiz doğrulama bağlantısını tıkla.
                </span>
                {verifySent ? (
                  <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                    <Mail className="size-3.5" /> Yeni doğrulama maili gönderildi
                  </span>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void handleResendVerify()}
                    disabled={resendingVerify}
                    className="mt-1 w-fit"
                  >
                    {resendingVerify
                      ? "Gönderiliyor…"
                      : "Doğrulama mailini tekrar gönder"}
                  </Button>
                )}
              </AlertDescription>
            </Alert>
          )}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">E-posta</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="ornek@nodrat.com"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Şifre</Label>
                <Link
                  href="/forgot-password"
                  className="text-xs text-primary hover:underline"
                >
                  Şifremi unuttum
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={12}
              />
            </div>
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Giriş yapılıyor…" : "Giriş yap"}
            </Button>
          </form>
        </CardContent>
        <CardContent className="border-t pt-4 text-sm text-muted-foreground">
          Hesabın yok mu?{" "}
          <Link href="/register" className="font-medium text-primary hover:underline">
            Kayıt ol
          </Link>
        </CardContent>
      </Card>
    </main>
  );
}
