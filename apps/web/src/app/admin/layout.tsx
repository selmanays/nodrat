"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { LogOut, Database, FileText, ServerCog, Scale } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV_ITEMS: Array<{ href: string; label: string; icon: React.ElementType }> = [
  { href: "/admin/sources", label: "Kaynaklar", icon: Database },
  { href: "/admin/articles", label: "Haberler", icon: FileText },
  { href: "/admin/queue", label: "Kuyruk", icon: ServerCog },
  { href: "/admin/legal", label: "Yasal", icon: Scale },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading, isAdmin, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  // Login sayfası AdminLayout'un dışında kalır
  const isLoginPage = pathname === "/admin/login";

  useEffect(() => {
    if (loading) return;
    if (isLoginPage) return;
    if (!user) {
      router.replace("/admin/login");
      return;
    }
    if (!isAdmin) {
      // Yetkisiz: ana sayfaya
      router.replace("/");
    }
  }, [user, isAdmin, loading, isLoginPage, router]);

  if (isLoginPage) {
    return <>{children}</>;
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Yükleniyor…</p>
      </div>
    );
  }

  if (!user || !isAdmin) {
    return null;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b bg-brand-950 text-white">
        <div className="container flex h-14 items-center justify-between gap-6">
          <div className="flex items-center gap-8">
            <Link
              href="/admin/sources"
              className="text-lg font-semibold tracking-tight"
            >
              Nodrat <span className="text-accent-300 text-xs">admin</span>
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
            <span className="text-brand-200">{user.email}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => signOut().then(() => router.replace("/admin/login"))}
              className="text-brand-100 hover:bg-brand-700 hover:text-white"
            >
              <LogOut className="h-4 w-4" />
              Çıkış
            </Button>
          </div>
        </div>
      </header>

      <main className="container flex-1 py-8">{children}</main>
    </div>
  );
}
