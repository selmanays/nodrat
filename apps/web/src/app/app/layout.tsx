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

// #800 S1A — Chat-only navigation. Form modu, eski geçmiş, kayıtlı sayfalar
// kaldırıldı; tek erişim noktası /app/chat (Perplexity-style sohbet).
const NAV_ITEMS: Array<{ href: string; label: string; icon: React.ElementType }> = [
  { href: "/app/chat", label: "Sohbet", icon: MessageSquare },
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

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b bg-background">
        <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between gap-6 px-4 md:px-6">
          <div className="flex items-center gap-8">
            <Link
              href="/app/generate"
              aria-label="Nodrat — anasayfaya dön"
              className="flex items-center"
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
                      "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm transition-colors",
                      active
                        ? "bg-secondary text-secondary-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <Icon className="size-4" />
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm">
            {quota && (
              <div className="flex items-center gap-1.5 rounded-full bg-muted px-3 py-1">
                <Zap className="size-3.5 text-primary" />
                <span className="font-mono tabular-nums">
                  {quota.remaining}
                  <span className="text-muted-foreground">/{quota.limit}</span>
                </span>
                <Badge variant="outline" className="text-[10px]">
                  {quota.tier}
                </Badge>
              </div>
            )}
            <Link
              href="/app/me"
              aria-label="Hesabım"
              className={cn(
                "flex items-center gap-1.5 rounded-full px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                pathname === "/app/me" && "bg-secondary text-secondary-foreground",
              )}
            >
              <User className="size-3.5" />
              <span className="hidden sm:inline">{user.email}</span>
              <span className="sm:hidden">Hesabım</span>
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
        <main className="flex-1 px-4 py-6 md:px-6 md:py-8">
          <div className="mx-auto w-full max-w-7xl">{children}</div>
        </main>
      </ConsentGate>
    </div>
  );
}
