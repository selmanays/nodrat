"use client";

/**
 * Admin layout — shadcn Sidebar pattern (#275, MVP-1.3)
 *
 * Preset b1VlIttI (radix-luma) + sidebar primitive. Tutarlı container
 * genişlikleri (her sayfa kendi içinde max-w yönetir).
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { useEffect } from "react";
import {
  Asterisk,
  Boxes,
  Brain,
  ChevronRight,
  CreditCard,
  HeartPulse,
  ImageIcon,
  LayoutDashboard,
  Logs,
  LogOut,
  Newspaper,
  Rss,
  Scale,
  Settings,
  Shield,
  SquareActivity,
  Users,
} from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { SETTINGS_GROUPS } from "@/lib/settings-groups";

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
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
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
import { ThemeToggle } from "@/components/theme-toggle";
type NavItem = {
  href: string;
  label: string;
  icon: React.ElementType;
  exact?: boolean;
  items?: { href: string; label: string }[];
};

const NAV_PRIMARY: NavItem[] = [
  { href: "/admin", label: "Özet", icon: LayoutDashboard, exact: true },
  { href: "/admin/sources", label: "Kaynaklar", icon: Rss },
  { href: "/admin/articles", label: "Haberler", icon: Newspaper },
  { href: "/admin/media", label: "Görseller", icon: ImageIcon },
  { href: "/admin/queue", label: "Kuyruk", icon: Logs },
  { href: "/admin/users", label: "Kullanıcılar", icon: Users },
];

const NAV_OBSERVABILITY: NavItem[] = [
  { href: "/admin/observability", label: "Sistem Durumu", icon: HeartPulse },
  { href: "/admin/rag", label: "RAG İzlencesi", icon: SquareActivity },
  { href: "/admin/sft", label: "SFT Pipeline", icon: Brain },
  { href: "/admin/audit", label: "Denetim", icon: Shield },
  { href: "/admin/clusters", label: "Kümeler", icon: Boxes },
];

const NAV_CONFIG: NavItem[] = [
  {
    href: "/admin/settings",
    label: "Ayarlar",
    icon: Settings,
    items: SETTINGS_GROUPS.map((g) => ({
      href: `/admin/settings/${g.slug}`,
      label: g.label,
    })),
  },
  { href: "/admin/prompts", label: "İstemler", icon: Asterisk },
  { href: "/admin/plans", label: "Planlar", icon: CreditCard },
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
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" asChild>
                <Link href="/admin">
                  <div className="flex aspect-square size-8 shrink-0 items-center justify-center rounded-full bg-primary text-[#00F2B1] dark:bg-[#00F2B1] dark:text-primary-foreground">
                    <Logo variant="mark" className="size-4" />
                  </div>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-medium">Nodrat</span>
                    <span className="truncate text-xs text-muted-foreground">
                      Yönetim Merkezi
                    </span>
                  </div>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
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
                    className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                  >
                    <Avatar className="size-8 shrink-0 rounded-full">
                      <AvatarFallback className="rounded-full bg-primary text-xs text-primary-foreground">
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
          <div
            role="separator"
            aria-orientation="vertical"
            className="mr-2 h-4 w-px shrink-0 self-center bg-border"
          />
          <BreadcrumbBar pathname={pathname} />
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
          </div>
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
          {items.map((item) => {
            const { href, label: itemLabel, icon: Icon, exact, items: subItems } = item;
            const active = exact
              ? pathname === href
              : pathname?.startsWith(href);

            if (subItems && subItems.length > 0) {
              return (
                <Collapsible
                  key={href}
                  asChild
                  defaultOpen={!!active}
                  className="group/collapsible"
                >
                  <SidebarMenuItem>
                    <CollapsibleTrigger asChild>
                      <SidebarMenuButton tooltip={itemLabel}>
                        <Icon />
                        <span>{itemLabel}</span>
                        <ChevronRight className="ml-auto transition-transform group-data-[state=open]/collapsible:rotate-90" />
                      </SidebarMenuButton>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <SidebarMenuSub>
                        {subItems.map((sub) => (
                          <SidebarMenuSubItem key={sub.href}>
                            <SidebarMenuSubButton
                              asChild
                              isActive={pathname === sub.href}
                            >
                              <Link href={sub.href}>
                                <span>{sub.label}</span>
                              </Link>
                            </SidebarMenuSubButton>
                          </SidebarMenuSubItem>
                        ))}
                      </SidebarMenuSub>
                    </CollapsibleContent>
                  </SidebarMenuItem>
                </Collapsible>
              );
            }

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
  media: "Görseller",
  queue: "Kuyruk",
  users: "Kullanıcılar",
  rag: "RAG İzlencesi",
  audit: "Denetim",
  settings: "Ayarlar",
  prompts: "İstemler",
  legal: "Yasal",
};

function getSegmentLabel(seg: string, prev: string | undefined): string {
  if (prev === "settings") {
    const g = SETTINGS_GROUPS.find((s) => s.slug === seg);
    if (g) return g.label;
  }
  return PATH_LABELS[seg] ?? seg;
}

function BreadcrumbBar({ pathname }: { pathname: string | null }) {
  if (!pathname) return null;
  const segments = pathname.split("/").filter(Boolean);
  return (
    <Breadcrumb>
      <BreadcrumbList>
        {segments.map((seg, idx) => {
          const isLast = idx === segments.length - 1;
          const label = getSegmentLabel(seg, segments[idx - 1]);
          const href = "/" + segments.slice(0, idx + 1).join("/");
          return (
            <React.Fragment key={seg}>
              {idx > 0 && <BreadcrumbSeparator />}
              <BreadcrumbItem>
                {isLast ? (
                  <BreadcrumbPage>{label}</BreadcrumbPage>
                ) : (
                  <BreadcrumbLink asChild>
                    <Link href={href}>{label}</Link>
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </React.Fragment>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
