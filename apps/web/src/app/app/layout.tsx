"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CreditCard, LogOut, MessageSquare, Palette, User, Zap } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Logo } from "@/components/brand/logo";
import { EmailVerifyBanner } from "@/components/email-verify-banner";
import { ConsentGate } from "@/components/consent/consent-gate";
import { cn } from "@/lib/utils";
import { getMyQuota, type QuotaResponse, ApiException } from "@/lib/api";

// #800 S1A — Research-only navigation. Form modu, eski geçmiş, kayıtlı sayfalar
// kaldırıldı; tek erişim noktası /app/research (Perplexity-style sohbet).
const NAV_ITEMS: Array<{ href: string; label: string; icon: React.ElementType }> = [
  { href: "/app/research", label: "Araştırma", icon: MessageSquare },
  { href: "/app/style-profiles", label: "Stil profilleri", icon: Palette },
  { href: "/app/billing", label: "Plan", icon: CreditCard },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [quota, setQuota] = useState<QuotaResponse | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
    }
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    getMyQuota()
      .then(setQuota)
      .catch((err: ApiException) => {
        // Silent fail — quota header opsiyonel
        console.warn("quota fetch failed", err);
      });
  }, [user, pathname]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Yükleniyor…</p>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  // S1F (#800 / #804): research sayfası tam-genişlik (max-w-7xl + padding kaldırılır)
  const isResearch = pathname?.startsWith("/app/research");

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <header className="z-10 shrink-0 border-b bg-background">
        <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between gap-3 px-3 md:gap-6 md:px-6">
          <div className="flex min-w-0 items-center gap-4 md:gap-8">
            <Link
              href="/app/research"
              aria-label="Nodrat — anasayfaya dön"
              className="flex shrink-0 items-center"
            >
              <Logo variant="wordmark" size="md" />
            </Link>
            <nav className="flex items-center gap-1">
              {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
                const active = pathname?.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={cn(
                      "flex items-center gap-1.5 rounded-full px-2 py-1.5 text-sm transition-colors md:px-3",
                      active
                        ? "bg-secondary text-secondary-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <Icon className="size-4 shrink-0" />
                    <span className="hidden sm:inline">{label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex min-w-0 items-center gap-2 text-sm md:gap-3">
            {quota && (
              <div className="flex shrink-0 items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 md:px-3">
                <Zap className="size-3.5 shrink-0 text-primary" />
                <span className="font-mono tabular-nums">
                  {quota.remaining}
                  <span className="text-muted-foreground">/{quota.limit}</span>
                </span>
                <Badge variant="outline" className="hidden text-[10px] sm:inline-flex">
                  {quota.tier}
                </Badge>
              </div>
            )}
            <Link
              href="/app/me"
              aria-label="Hesabım"
              className={cn(
                "flex min-w-0 items-center gap-1.5 rounded-full px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                pathname === "/app/me" && "bg-secondary text-secondary-foreground",
              )}
            >
              <User className="size-3.5 shrink-0" />
              <span className="hidden max-w-[180px] truncate md:inline">
                {user.email}
              </span>
              <span className="md:hidden">Hesabım</span>
            </Link>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => signOut().then(() => router.replace("/login"))}
              aria-label="Çıkış"
            >
              <LogOut />
            </Button>
          </div>
        </div>
      </header>

      {!user.email_verified && <EmailVerifyBanner email={user.email} />}

      <ConsentGate>
        {isResearch ? (
          // Sabit calc(100vh-…) yerine flex zinciri: header + e-posta
          // banner'ı ne yer kaplarsa kaplasın research kalan alana oturur,
          // scroll research'in kendi içinde (mesaj listesi) kalır.
          <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
            {children}
          </main>
        ) : (
          <main className="min-h-0 flex-1 overflow-y-auto px-4 py-6 md:px-6 md:py-8">
            <div className="mx-auto w-full max-w-7xl">{children}</div>
          </main>
        )}
      </ConsentGate>
    </div>
  );
}
