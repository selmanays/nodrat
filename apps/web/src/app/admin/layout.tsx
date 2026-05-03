"use client";

/**
 * Admin layout — shadcn Sidebar pattern (#275, MVP-1.3)
 *
 * Preset b1VlIttI (radix-luma) + sidebar primitive. Tutarlı container
 * genişlikleri (her sayfa kendi içinde max-w yönetir).
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  Database,
  FileCode,
  FileText,
  History,
  Home,
  LogOut,
  Scale,
  ServerCog,
  Settings,
  Sparkles,
  Users,
} from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { Logo } from "@/components/brand/logo";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Avatar,
  AvatarFallback,
} from "@/components/ui/avatar";
type NavItem = {
  href: string;
  label: string;
  icon: React.ElementType;
  exact?: boolean;
};

const NAV_PRIMARY: NavItem[] = [
  { href: "/admin", label: "Özet", icon: Home, exact: true },
  { href: "/admin/sources", label: "Kaynaklar", icon: Database },
  { href: "/admin/articles", label: "Haberler", icon: FileText },
  { href: "/admin/queue", label: "Kuyruk", icon: ServerCog },
  { href: "/admin/users", label: "Kullanıcılar", icon: Users },
];

const NAV_OBSERVABILITY: NavItem[] = [
  { href: "/admin/rag", label: "RAG Monitor", icon: Sparkles },
  { href: "/admin/audit", label: "Audit", icon: History },
];

const NAV_CONFIG: NavItem[] = [
  { href: "/admin/settings", label: "Ayarlar", icon: Settings },
  { href: "/admin/prompts", label: "Prompts", icon: FileCode },
  { href: "/admin/legal", label: "Yasal", icon: Scale },
];

function getInitials(email?: string | null): string {
  if (!email) return "??";
  const local = email.split("@")[0] || "";
  return local.slice(0, 2).toUpperCase();
}

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading, isAdmin, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const isLoginPage = pathname === "/admin/login";

  useEffect(() => {
    if (loading) return;
    if (isLoginPage) return;
    if (!user) {
      router.replace("/admin/login");
      return;
    }
    if (!isAdmin) {
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
    <SidebarProvider defaultOpen>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <Link
            href="/admin"
            className="flex items-center gap-2 px-2 py-2"
            aria-label="Nodrat admin"
          >
            <Logo variant="wordmark" size="md" />
            <span className="ml-1 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-700 group-data-[collapsible=icon]:hidden dark:text-amber-400">
              admin
            </span>
          </Link>
        </SidebarHeader>

        <SidebarContent>
          <NavGroup label="Genel" items={NAV_PRIMARY} pathname={pathname} />
          <NavGroup
            label="Gözlem"
            items={NAV_OBSERVABILITY}
            pathname={pathname}
          />
          <NavGroup label="Sistem" items={NAV_CONFIG} pathname={pathname} />
        </SidebarContent>

        <SidebarFooter>
          <SidebarMenu>
            <SidebarMenuItem>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuButton
                    size="lg"
                    className="data-[state=open]:bg-sidebar-accent"
                  >
                    <Avatar className="h-8 w-8 rounded-md">
                      <AvatarFallback className="rounded-md bg-primary text-xs text-primary-foreground">
                        {getInitials(user.email)}
                      </AvatarFallback>
                    </Avatar>
                    <div className="grid flex-1 text-left text-sm leading-tight">
                      <span className="truncate font-medium">{user.email}</span>
                      <span className="truncate text-xs text-muted-foreground">
                        super_admin
                      </span>
                    </div>
                  </SidebarMenuButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  side="right"
                  align="end"
                  className="min-w-56"
                >
                  <DropdownMenuLabel className="font-normal">
                    <div className="grid text-sm">
                      <span className="font-medium">{user.email}</span>
                      <span className="text-xs text-muted-foreground">
                        Sistem yöneticisi
                      </span>
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={() =>
                      signOut().then(() => router.replace("/admin/login"))
                    }
                    className="text-destructive focus:text-destructive"
                  >
                    <LogOut className="mr-2 h-4 w-4" />
                    Çıkış yap
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>

        <SidebarRail />
      </Sidebar>

      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-background px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-2 h-4" />
          <BreadcrumbBar pathname={pathname} />
        </header>

        <main className="flex-1 px-4 py-6 md:px-6 md:py-8">
          <div className="mx-auto w-full max-w-7xl">{children}</div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}

function NavGroup({
  label,
  items,
  pathname,
}: {
  label: string;
  items: NavItem[];
  pathname: string | null;
}) {
  return (
    <SidebarGroup>
      <SidebarGroupLabel>{label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map(({ href, label: itemLabel, icon: Icon, exact }) => {
            const active = exact
              ? pathname === href
              : pathname?.startsWith(href);
            return (
              <SidebarMenuItem key={href}>
                <SidebarMenuButton asChild isActive={!!active} tooltip={itemLabel}>
                  <Link href={href}>
                    <Icon />
                    <span>{itemLabel}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            );
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

const PATH_LABELS: Record<string, string> = {
  admin: "Yönetim",
  sources: "Kaynaklar",
  articles: "Haberler",
  queue: "Kuyruk",
  users: "Kullanıcılar",
  rag: "RAG Monitor",
  audit: "Audit",
  settings: "Ayarlar",
  prompts: "Prompts",
  legal: "Yasal",
};

function BreadcrumbBar({ pathname }: { pathname: string | null }) {
  if (!pathname) return null;
  const segments = pathname.split("/").filter(Boolean);
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm">
      {segments.map((seg, idx) => {
        const isLast = idx === segments.length - 1;
        const label = PATH_LABELS[seg] || seg;
        return (
          <span key={seg} className="flex items-center gap-1">
            {idx > 0 && <span className="text-muted-foreground">/</span>}
            <span
              className={
                isLast ? "font-medium" : "text-muted-foreground"
              }
            >
              {label}
            </span>
          </span>
        );
      })}
    </nav>
  );
}
