"use client";

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

export default function AdminLoginPage() {
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
      if (user.role !== "super_admin") {
        toast.error("Bu hesap admin paneline erişemez.");
        return;
      }
      toast.success("Hoş geldin");
      router.replace("/admin/sources");
    } catch (error) {
      const apiError = error as ApiException;
      toast.error(apiError.message || "Giriş başarısız");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-4">
          <div className="flex items-center gap-3">
            <div className="flex aspect-square size-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Logo variant="mark" size="sm" tone="inverse" />
            </div>
            <div className="grid leading-tight">
              <span className="font-semibold">nodrat</span>
              <span className="text-[10px] font-medium uppercase tracking-wider text-amber-600 dark:text-amber-400">
                admin
              </span>
            </div>
          </div>
          <div className="space-y-1.5">
            <CardTitle className="text-xl">Yönetici girişi</CardTitle>
            <CardDescription>
              Yönetici hesabınla giriş yap. KVKK aydınlatma metni okundu kabul edilir.
            </CardDescription>
          </div>
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
                placeholder="admin@nodrat.com"
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
      </Card>
    </main>
  );
}
