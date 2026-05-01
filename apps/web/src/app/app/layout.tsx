"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Bookmark, History, LogOut, Sparkles, Zap } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { getMyQuota, type QuotaResponse, ApiException } from "@/lib/api";

const NAV_ITEMS: Array<{ href: string; label: string; icon: React.ElementType }> = [
  { href: "/app/generate", label: "Yeni üretim", icon: Sparkles },
  { href: "/app/generations", label: "Geçmiş", icon: History },
  { href: "/app/saved", label: "Kayıtlı", icon: Bookmark },
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
      <header className="border-b bg-brand-950 text-white">
        <div className="container flex h-14 items-center justify-between gap-6">
          <div className="flex items-center gap-8">
            <Link
              href="/app/generate"
              className="text-lg font-semibold tracking-tight"
            >
              Nodrat
            </Link>
            <nav className="flex items-center gap-1">
              {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
                const active = pathname?.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={cn(
                      "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors",
                      active
                        ? "bg-brand-700 text-white"
                        : "text-brand-100 hover:bg-brand-700/40 hover:text-white",
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm">
            {quota && (
              <div className="flex items-center gap-1.5 rounded-md bg-brand-700/50 px-3 py-1">
                <Zap className="h-3.5 w-3.5 text-accent-300" />
                <span className="text-brand-100">
                  <span className="font-mono text-white">{quota.remaining}</span>
                  <span className="text-brand-300">/{quota.limit}</span>
                </span>
                <Badge
                  variant="outline"
                  className="border-brand-300/40 bg-transparent text-brand-200 text-[10px]"
                >
                  {quota.tier}
                </Badge>
              </div>
            )}
            <span className="text-brand-200 text-xs">{user.email}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => signOut().then(() => router.replace("/login"))}
              className="text-brand-100 hover:bg-brand-700 hover:text-white"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </header>

      <main className="container flex-1 py-8">{children}</main>
    </div>
  );
}
