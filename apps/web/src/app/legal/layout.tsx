import Link from "next/link";
import type { Metadata } from "next";
import { ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Yasal — Nodrat",
  description: "Nodrat yasal dokümanları, kullanım şartları, KVKK aydınlatma, takedown formları.",
};

const NAV: Array<{ href: string; label: string }> = [
  { href: "/legal/tos", label: "Kullanım Şartları" },
  { href: "/legal/privacy", label: "Gizlilik Politikası" },
  { href: "/legal/kvkk-aydinlatma", label: "KVKK Aydınlatma" },
  { href: "/legal/cookies", label: "Çerez Politikası" },
  { href: "/legal/scraping", label: "Tarama Politikası" },
];

const FORMS: Array<{ href: string; label: string }> = [
  { href: "/legal/abuse", label: "Kötüye Kullanım Bildir" },
  { href: "/legal/takedown", label: "5651 Kaldırma Talebi" },
  { href: "/legal/copyright", label: "Telif (FSEK) İhlali" },
  { href: "/legal/privacy-request", label: "KVKK md.11 Başvuru" },
];

export default function LegalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container flex h-14 items-center justify-between gap-4">
          <Link
            href="/"
            className="text-lg font-semibold tracking-tight"
          >
            Nodrat <span className="text-xs text-muted-foreground">/ Yasal</span>
          </Link>
          <Button asChild variant="ghost" size="sm">
            <Link href="/">
              <ArrowLeft className="h-4 w-4" />
              Ana sayfa
            </Link>
          </Button>
        </div>
      </header>

      <div className="container py-8">
        <div className="grid gap-8 lg:grid-cols-[260px_1fr]">
          <aside className="space-y-6 lg:sticky lg:top-6 self-start">
            <div>
              <h3 className="mb-3 text-xs font-semibold uppercase text-muted-foreground">
                Politikalar
              </h3>
              <nav className="space-y-1">
                {NAV.map(({ href, label }) => (
                  <Link
                    key={href}
                    href={href}
                    className="block rounded-xl px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    {label}
                  </Link>
                ))}
              </nav>
            </div>
            <div>
              <h3 className="mb-3 text-xs font-semibold uppercase text-muted-foreground">
                Talepler
              </h3>
              <nav className="space-y-1">
                {FORMS.map(({ href, label }) => (
                  <Link
                    key={href}
                    href={href}
                    className="block rounded-xl px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    {label}
                  </Link>
                ))}
              </nav>
            </div>
            <div className="rounded-2xl bg-muted/50 p-4 text-xs text-muted-foreground">
              <p className="font-medium text-foreground mb-1">Hızlı iletişim</p>
              <p>
                Yasal:{" "}
                <a
                  href="mailto:legal@nodrat.com"
                  className="text-primary hover:underline"
                >
                  legal@nodrat.com
                </a>
              </p>
              <p>
                DPO:{" "}
                <a
                  href="mailto:dpo@nodrat.com"
                  className="text-primary hover:underline"
                >
                  dpo@nodrat.com
                </a>
              </p>
            </div>
          </aside>

          <main className="prose prose-slate dark:prose-invert max-w-none">
            {children}
          </main>
        </div>
      </div>

      <footer className="mt-12 border-t py-6 text-center text-xs text-muted-foreground">
        <p>
          Nodrat MVP-1 — Bu dokümanlar taslaktır, yasal danışman onayı sonrası
          güncellenecektir.
        </p>
      </footer>
    </div>
  );
}
