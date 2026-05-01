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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/brand/logo";
import { useAuth } from "@/lib/auth-context";
import { ApiException } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const user = await signIn({ email, password });
      toast.success("Hoş geldin");
      // super_admin → admin paneli, normal kullanıcı → /app
      router.replace(user.role === "super_admin" ? "/admin/sources" : "/app/generate");
    } catch (error) {
      const apiError = error as ApiException;
      toast.error(apiError.message || "Giriş başarısız");
    } finally {
      setSubmitting(false);
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
              <Label htmlFor="password">Şifre</Label>
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
