"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { AlertTriangle, Mail } from "lucide-react";
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
    <main className="flex min-h-screen items-center justify-center bg-brand-50 p-4 dark:bg-brand-950">
      <Card className="w-full max-w-md">
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
            <div className="mb-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950/40">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="font-medium text-amber-900 dark:text-amber-100">
                    E-posta doğrulanmamış
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Hesabını kullanmak için <strong>{email}</strong> adresine
                    gönderdiğimiz doğrulama bağlantısını tıkla.
                  </p>
                  {verifySent ? (
                    <p className="mt-2 flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-400">
                      <Mail className="h-3 w-3" /> Yeni doğrulama maili gönderildi
                    </p>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void handleResendVerify()}
                      disabled={resendingVerify}
                      className="mt-2 border-amber-300 text-amber-900 hover:bg-amber-100"
                    >
                      {resendingVerify
                        ? "Gönderiliyor…"
                        : "Doğrulama mailini tekrar gönder"}
                    </Button>
                  )}
                </div>
              </div>
            </div>
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
                  className="text-xs text-brand-700 hover:underline"
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
          <Link href="/register" className="font-medium text-brand-700 hover:underline">
            Kayıt ol
          </Link>
        </CardContent>
      </Card>
    </main>
  );
}
