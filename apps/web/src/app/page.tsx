import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  ScrollText,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
  Zap,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Logo } from "@/components/brand/logo";

/**
 * Landing page — #299 redesign (MVP-1.6 carry).
 *
 * Sections:
 *  1. Header (logo, login/register)
 *  2. Hero (tagline + dual CTA — kayıt + anonim arama)
 *  3. Feature highlights (4 kart)
 *  4. How it works (3 adım)
 *  5. Pricing teaser (4 tier + 'detay için iletişim')
 *  6. Final CTA
 *  7. Footer (legal + bot link)
 *
 * Pre-launch noindex layout.tsx'te.
 * docs/design/ux-wireframes.md §6, docs/strategy/pricing-strategy.md
 */

export default function HomePage() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main>
        <Hero />
        <Features />
        <HowItWorks />
        <Pricing />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}

function Header() {
  return (
    <header className="border-b">
      <div className="container max-w-6xl py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center">
          <Logo variant="wordmark" size="sm" className="h-7 w-auto" />
          <span className="sr-only">Nodrat</span>
        </Link>
        <nav className="flex items-center gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link href="/ara">
              <Search className="mr-1 h-3.5 w-3.5" />
              Haber ara
            </Link>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link href="/login">Giriş yap</Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/register">
              Ücretsiz başla
              <ArrowRight className="ml-1 h-3.5 w-3.5" />
            </Link>
          </Button>
        </nav>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="container max-w-6xl py-16 md:py-24">
      <div className="max-w-3xl mx-auto text-center space-y-6">
        <Badge variant="outline" className="text-xs">
          Türkçe gündem için editör odaklı yapay zeka
        </Badge>
        <h1 className="text-4xl md:text-6xl font-bold tracking-tight leading-tight">
          Gündem haberlerini{" "}
          <span className="text-primary">kaynaklı X içeriklerine</span>{" "}
          dönüştür
        </h1>
        <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto leading-relaxed">
          Halüsinasyon koruması, KVKK uyumlu PII redaction, FSEK uyumlu kaynak
          atıfları. ChatGPT&apos;nin yanında — gündem için özel araç.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-4">
          <Button asChild size="lg">
            <Link href="/register">
              Ücretsiz hesap aç
              <ArrowRight className="ml-1 h-4 w-4" />
            </Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/ara">
              <Search className="mr-1 h-4 w-4" />
              Önce haber ara (kayıt yok)
            </Link>
          </Button>
        </div>
        <p className="text-xs text-muted-foreground pt-2">
          İlk 10 üretim ücretsiz · Kart bilgisi gerekmez · KVKK uyumlu
        </p>
      </div>
    </section>
  );
}

function Features() {
  const items = [
    {
      icon: ShieldCheck,
      title: "Halüsinasyon koruması",
      desc: "Üretim sadece doğrulanmış haber kartlarına dayanır. Kaynak yetersizse içerik üretilmez, alternatif önerilir.",
    },
    {
      icon: ScrollText,
      title: "Kaynaklı çıktı",
      desc: "Her paylaşıma orijinal yayıncı linki, FSEK uyumlu max 25 kelime alıntı. Yayıncıya trafik döner.",
    },
    {
      icon: FileText,
      title: "KVKK + PII redaction",
      desc: "LLM çağrısı öncesi kişisel veri otomatik gizlenir. Açık rıza akışı, 30 gün hard delete, soft delete default.",
    },
    {
      icon: Sparkles,
      title: "Editör odaklı, ChatGPT yanında",
      desc: "Tone, uzunluk, çıktı türü (X post / thread / özet / başlık önerisi) — sen seçer, AI uygular. Genel amaçlı asistanın yerine değil, yanında.",
    },
  ];
  return (
    <section className="border-t bg-muted/20">
      <div className="container max-w-6xl py-16">
        <div className="text-center mb-10 space-y-2">
          <h2 className="text-3xl font-semibold tracking-tight">
            Neden Nodrat?
          </h2>
          <p className="text-muted-foreground max-w-2xl mx-auto">
            Türkçe haber için tasarlandı — kaynak güvenliği, halü kontrolü ve
            yasal uyum &ldquo;sonradan eklendi&rdquo; değil, baştan tasarımda.
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {items.map(({ icon: Icon, title, desc }) => (
            <Card key={title}>
              <CardHeader className="pb-3">
                <Icon className="h-6 w-6 text-primary mb-2" />
                <CardTitle className="text-base">{title}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {desc}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  const steps = [
    {
      n: "1",
      title: "Gündemi otomatik topla",
      desc: "BBC, Evrensel, AA, Habertürk gibi 5+ Türkçe kaynak 15dk'da bir taranır. Robots.txt + paywall + telif kuralları otomatik enforce edilir.",
    },
    {
      n: "2",
      title: "İsteği yaz, AI üretsin",
      desc: "&ldquo;Bu hafta ekonomi gelişmeleri 3 X paylaşımı&rdquo; gibi. Tone (8 seçenek), uzunluk, çıktı türü senin elinde. Sonuç ~20 saniyede gelir.",
    },
    {
      n: "3",
      title: "Düzenle ve paylaş",
      desc: "Karakter sayacı, kaynak listesi, halü uyarıları görünür. Beğendiğini kaydet, beğenmediğini halü flag&apos;le — model gelişir.",
    },
  ];
  return (
    <section className="border-t">
      <div className="container max-w-6xl py-16">
        <div className="text-center mb-10 space-y-2">
          <h2 className="text-3xl font-semibold tracking-tight">
            Nasıl çalışır?
          </h2>
          <p className="text-muted-foreground">3 adımda gündem → X paylaşımı.</p>
        </div>
        <div className="grid gap-6 md:grid-cols-3">
          {steps.map(({ n, title, desc }) => (
            <div key={n} className="space-y-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary font-semibold">
                {n}
              </div>
              <h3 className="text-lg font-medium">{title}</h3>
              <p
                className="text-sm text-muted-foreground leading-relaxed"
                dangerouslySetInnerHTML={{ __html: desc }}
              />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Pricing() {
  const tiers = [
    {
      name: "Free",
      price: "0 TL",
      period: "/ay",
      desc: "Kayıtlı kullanıcı için kalıcı ücretsiz seviye.",
      features: ["10 üretim/ay", "Tüm output type", "Ton + uzunluk seçimi", "Tek kullanıcı"],
      cta: { href: "/register", label: "Ücretsiz başla" },
      highlight: false,
    },
    {
      name: "Starter",
      price: "249 TL",
      period: "/ay",
      desc: "Kişisel creator + freelancer için.",
      features: [
        "100 üretim/ay",
        "Geçmiş + favorilere kaydet",
        "Öncelikli sıra",
        "3 gün ücretsiz deneme",
      ],
      cta: { href: "/register", label: "Denemeye başla" },
      highlight: false,
    },
    {
      name: "Pro",
      price: "749 TL",
      period: "/ay",
      desc: "Profesyonel editör + ajans creator.",
      features: [
        "500 üretim/ay",
        "Stil profili (Faz 5)",
        "Karşılaştırmalı mod",
        "3 gün ücretsiz deneme",
      ],
      cta: { href: "/register", label: "Pro&apos;yu dene" },
      highlight: true,
    },
    {
      name: "Agency",
      price: "2.499 TL",
      period: "/ay",
      desc: "Ajans, marka, çoklu hesap.",
      features: [
        "2.500 üretim/ay × 3 koltuk",
        "Premium model erişimi",
        "Multi-brand stil profili",
        "7 gün ücretsiz deneme",
      ],
      cta: { href: "mailto:hello@nodrat.com?subject=Agency%20bilgi", label: "İletişime geç" },
      highlight: false,
    },
  ];

  return (
    <section className="border-t bg-muted/20">
      <div className="container max-w-6xl py-16">
        <div className="text-center mb-10 space-y-2">
          <h2 className="text-3xl font-semibold tracking-tight">
            Şeffaf fiyatlar
          </h2>
          <p className="text-muted-foreground max-w-2xl mx-auto">
            Hesap aç, ilk 10 üretim ücretsiz. İhtiyacın artarsa Starter veya Pro
            — istediğin zaman iptal et, kart bilgisi sadece deneme başlatırken.
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {tiers.map((t) => (
            <Card
              key={t.name}
              className={
                t.highlight
                  ? "border-primary shadow-md relative"
                  : ""
              }
            >
              {t.highlight && (
                <Badge className="absolute -top-2 left-4">En popüler</Badge>
              )}
              <CardHeader>
                <CardTitle className="text-lg">{t.name}</CardTitle>
                <div className="flex items-baseline gap-1">
                  <span className="text-3xl font-bold">{t.price}</span>
                  <span className="text-sm text-muted-foreground">
                    {t.period}
                  </span>
                </div>
                <CardDescription>{t.desc}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <ul className="space-y-2 text-sm">
                  {t.features.map((f) => (
                    <li key={f} className="flex items-start gap-2">
                      <CheckCircle2 className="h-4 w-4 text-primary mt-0.5 shrink-0" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
                <Button
                  asChild
                  variant={t.highlight ? "default" : "outline"}
                  className="w-full"
                  size="sm"
                >
                  <Link href={t.cta.href}>{t.cta.label}</Link>
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
        <p className="text-xs text-muted-foreground text-center mt-6">
          Yıllık ödemede 2 ay bedava (~%16.7 indirim) · TL primary, USD
          referans · Ödeme sayfası MVP-3
        </p>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="border-t">
      <div className="container max-w-4xl py-16 text-center space-y-5">
        <Zap className="h-10 w-10 mx-auto text-primary" />
        <h2 className="text-3xl font-semibold tracking-tight">
          Editör odaklı içerik üretimi 1 dakikada başlar
        </h2>
        <p className="text-muted-foreground max-w-2xl mx-auto">
          E-posta + şifre ile kayıt, anında 10 ücretsiz üretim hakkı. Kart
          istemez, e-posta doğrulamadan sonra hemen kullanmaya başlarsın.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <Button asChild size="lg">
            <Link href="/register">
              Ücretsiz hesap aç
              <ArrowRight className="ml-1 h-4 w-4" />
            </Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/ara">
              <Users className="mr-1 h-4 w-4" />
              Önce ürünü gör
            </Link>
          </Button>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t py-10">
      <div className="container max-w-6xl space-y-6">
        <div className="flex flex-col md:flex-row gap-4 md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <Logo variant="wordmark" size="sm" className="h-6 w-auto" />
            <span className="text-xs text-muted-foreground">
              · Editör odaklı haber içerik üretimi
            </span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <Link href="/legal/tos" className="hover:underline">
              Kullanım Şartları
            </Link>
            <Link href="/legal/privacy-policy" className="hover:underline">
              Gizlilik
            </Link>
            <Link href="/legal/kvkk-aydinlatma" className="hover:underline">
              KVKK Aydınlatma
            </Link>
            <Link href="/legal/cookies-policy" className="hover:underline">
              Çerezler
            </Link>
            <Link href="/legal/scraping-policy" className="hover:underline">
              Kaynak Politikası
            </Link>
            <Link href="/bot" className="hover:underline">
              Yayıncılar (NodratBot)
            </Link>
          </div>
        </div>
        <p className="text-xs text-muted-foreground max-w-3xl leading-relaxed border-t pt-4">
          <strong>Nodrat haber kaynağı değildir.</strong> Editör için yapay zeka
          destekli içerik üretim aracıdır. Tüm haber içerikleri orijinal
          yayıncıya atıflıdır; kaynak link'leri korunur. Çıktıların editör
          tarafından gözden geçirilmesi tavsiye edilir. KVKK + FSEK uyumlu
          tasarlandı.
        </p>
      </div>
    </footer>
  );
}
