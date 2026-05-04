import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Toaster } from "sonner";

import { CookieBanner } from "@/components/cookie-banner";
import { ThemeProvider } from "@/components/theme-provider";
import { AuthProvider } from "@/lib/auth-context";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

const inter = Inter({
  subsets: ["latin", "latin-ext"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: {
    default: "Nodrat — Editör odaklı üretim aracı",
    template: "%s | Nodrat",
  },
  description:
    "Türkçe gündemi kaynaklı X içeriklerine dönüştüren editör odaklı üretim aracı. ChatGPT yanında, gündem için özel araç.",
  keywords: ["nodrat", "x", "twitter", "gündem", "rag", "ai", "içerik üretimi"],
  authors: [{ name: "Nodrat" }],
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_APP_URL || "https://nodrat.com"
  ),
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
    ],
    shortcut: "/favicon.svg",
    apple: "/favicon.svg",
  },
  openGraph: {
    type: "website",
    locale: "tr_TR",
    url: "/",
    title: "Nodrat",
    description:
      "Türkçe gündemden kaynaklı X içerikleri üret — editör odaklı.",
    siteName: "Nodrat",
    images: [
      {
        url: "/og-default.svg",
        width: 1200,
        height: 630,
        alt: "Nodrat — Editör odaklı üretim aracı",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Nodrat",
    description:
      "Türkçe gündemden kaynaklı X içerikleri üret — editör odaklı.",
    images: ["/og-default.svg"],
  },
  // 🚫 PRE-LAUNCH: arama motorlarında indekslenmemeli (kullanıcı talebi)
  // Production launch sonrası true:true yap.
  robots: {
    index: false,
    follow: false,
    googleBot: {
      index: false,
      follow: false,
      noimageindex: true,
    },
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="tr" className={inter.variable} suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <AuthProvider>
            <TooltipProvider>
              {children}
              <CookieBanner />
              <Toaster richColors position="top-right" />
            </TooltipProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
