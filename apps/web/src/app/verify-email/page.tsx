"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Logo } from "@/components/brand/logo";
import { ApiException, apiFetch } from "@/lib/api";

type VerifyState =
  | { status: "loading" }
  | { status: "success"; email: string }
  | { status: "error"; message: string };

export default function VerifyEmailPage() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [state, setState] = useState<VerifyState>({ status: "loading" });

  useEffect(() => {
    if (!token) {
      setState({
        status: "error",
        message:
          "Doğrulama bağlantısı eksik. E-postandaki bağlantıyı tekrar kullan.",
      });
      return;
    }

    void verify(token);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function verify(rawToken: string) {
    try {
      const result = await apiFetch<{
        user_id: string;
        email: string;
        email_verified: boolean;
      }>("/auth/verify", {
        method: "POST",
        body: { token: rawToken },
        skipAuth: true,
      });
      setState({ status: "success", email: result.email });
    } catch (error) {
      const apiError = error as ApiException;
      setState({
        status: "error",
        message:
          apiError.message ||
          "Doğrulama başarısız. Bağlantı süresi dolmuş olabilir.",
      });
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-brand-50 p-4 dark:bg-brand-950">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-3">
          <Link href="/" aria-label="Nodrat anasayfasına dön" className="inline-flex">
            <Logo variant="wordmark" size="md" />
          </Link>
          <CardTitle className="text-2xl">E-posta doğrulama</CardTitle>
        </CardHeader>
        <CardContent>
          {state.status === "loading" && (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <Loader2 className="h-8 w-8 animate-spin text-brand-700" />
              <p className="text-sm text-muted-foreground">Doğrulanıyor…</p>
            </div>
          )}

          {state.status === "success" && (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <CheckCircle2 className="h-12 w-12 text-emerald-500" />
              <CardTitle className="text-lg">Doğrulama tamamlandı</CardTitle>
              <CardDescription>
                <strong>{state.email}</strong> adresi başarıyla doğrulandı.
                Artık giriş yapabilirsin.
              </CardDescription>
              <Link href="/login" className="mt-4 w-full">
                <Button className="w-full">Giriş yap</Button>
              </Link>
            </div>
          )}

          {state.status === "error" && (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <XCircle className="h-12 w-12 text-red-500" />
              <CardTitle className="text-lg">Doğrulama başarısız</CardTitle>
              <CardDescription>{state.message}</CardDescription>
              <div className="mt-4 flex w-full flex-col gap-2">
                <Link href="/login">
                  <Button variant="outline" className="w-full">
                    Giriş sayfasına git
                  </Button>
                </Link>
                <p className="text-xs text-muted-foreground">
                  Yeni doğrulama maili için giriş yapmayı dene — sistem
                  otomatik yeniden gönderecektir.
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
