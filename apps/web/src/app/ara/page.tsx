"use client";

/**
 * #261 Phase B — Public anonim haber arama sayfası (/ara)
 *
 * - Anonim erişim (auth yok)
 * - IP rate limit 10 req/min — backend tarafında
 * - FSEK uyumlu: title + 250 char özet + "Kaynağa git" link
 * - Register CTA: "Kendi içeriğini üret → kayıt ol"
 *
 * docs/strategy/pricing-strategy.md §2.1b — Anonim Ziyaretçi
 */

import Link from "next/link";
import { FormEvent, useState } from "react";
import { ArrowRight, ExternalLink, Search, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  ApiException,
  publicSearch,
  type PublicSearchResponse,
} from "@/lib/api";

const SAMPLE_QUERIES = [
  "Trump İran müzakereleri",
  "Türkiye ekonomi enflasyon",
  "Avrupa Birliği yeşil mutabakat",
  "yapay zeka regülasyonları",
  "deprem yardım koordinasyonu",
];

export default function PublicSearchPage() {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<PublicSearchResponse | null>(null);

  async function runSearch(query: string) {
    if (query.trim().length < 2) {
      toast.error("En az 2 karakter girin");
      return;
    }
    setBusy(true);
    try {
      const r = await publicSearch(query.trim(), 15);
      setData(r);
      if (r.items.length === 0) {
        toast.message("Bu sorgu için sonuç yok — başka kelime dene");
      }
    } catch (e) {
      const ae = e as ApiException;
      if (ae.status === 429) {
        toast.error("Çok hızlı arama yaptın — 1 dakika bekle");
      } else {
        toast.error(ae.message || "Arama başarısız");
      }
    } finally {
      setBusy(false);
    }
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void runSearch(q);
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container max-w-5xl py-4 flex items-center justify-between">
          <Link href="/" className="font-semibold text-lg">
            nodrat
          </Link>
          <div className="flex gap-2">
            <Button asChild variant="ghost" size="sm">
              <Link href="/login">Giriş yap</Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/register">
                Ücretsiz kayıt ol
                <ArrowRight className="ml-1 h-3 w-3" />
              </Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="container max-w-5xl py-10 space-y-8">
        <div className="text-center space-y-2">
          <h1 className="text-3xl md:text-4xl font-bold">
            Türkçe gündem arşivinde ara
          </h1>
          <p className="text-muted-foreground">
            Editör odaklı haber arama — kaynaklı, tarafsız, FSEK uyumlu özetler
          </p>
        </div>

        <form onSubmit={handleSubmit} className="max-w-2xl mx-auto">
          <div className="flex gap-2">
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="örn. Trump İran müzakereleri"
              autoFocus
              maxLength={200}
              className="text-base h-12"
            />
            <Button type="submit" size="lg" disabled={busy || !q.trim()}>
              <Search className="mr-1 h-4 w-4" />
              {busy ? "Aranıyor…" : "Ara"}
            </Button>
          </div>
        </form>

        {!data && !busy && (
          <div className="max-w-2xl mx-auto space-y-2">
            <p className="text-xs font-medium text-muted-foreground">
              ÖRNEK SORGULAR
            </p>
            {SAMPLE_QUERIES.map((s) => (
              <button
                key={s}
                onClick={() => {
                  setQ(s);
                  void runSearch(s);
                }}
                className="block w-full text-left rounded-md border bg-muted/30 px-3 py-2 text-sm hover:bg-muted"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {data && (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>
                <strong className="text-foreground">{data.total}</strong> sonuç
                — &ldquo;{data.query}&rdquo;
              </span>
              <span>kalan kota: {data.rate_limit_remaining}</span>
            </div>

            {data.items.map((it) => (
              <Card key={it.id}>
                <CardContent className="p-4 space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="font-medium leading-snug">{it.title}</h2>
                    {it.country && (
                      <Badge variant="outline" className="text-[10px] shrink-0">
                        {it.country}
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground line-clamp-3">
                    {it.summary}
                  </p>
                  <div className="flex items-center justify-between text-xs pt-1">
                    {it.published_at && (
                      <span className="text-muted-foreground">
                        {new Date(it.published_at).toLocaleString("tr-TR")}
                      </span>
                    )}
                    {it.source_url && (
                      <a
                        href={it.source_url}
                        target="_blank"
                        rel="noopener noreferrer nofollow"
                        className="text-primary hover:underline flex items-center gap-1"
                      >
                        Kaynağa git
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}

            {/* Conversion CTA */}
            <Card className="bg-primary/5 border-primary/30">
              <CardContent className="p-6 text-center space-y-3">
                <Sparkles className="h-8 w-8 mx-auto text-primary" />
                <h3 className="text-lg font-semibold">
                  Bu konuda kendi X paylaşımını üretmek ister misin?
                </h3>
                <p className="text-sm text-muted-foreground max-w-md mx-auto">
                  Kayıt ol — gündem kartlarını kullanarak senin tonunda,
                  istediğin uzunlukta içerik üret. İlk 5 üretim ücretsiz.
                </p>
                <Button asChild>
                  <Link href="/register">
                    Ücretsiz kayıt ol
                    <ArrowRight className="ml-1 h-4 w-4" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
          </div>
        )}
      </main>

      <footer className="border-t py-6 mt-10">
        <div className="container max-w-5xl text-center text-xs text-muted-foreground space-y-1">
          <p>
            Nodrat haber kaynağı değildir — editör için yapay zeka destekli
            içerik üretim aracıdır. Tüm haber içerikleri orijinal kaynağa
            atıflıdır.
          </p>
          <p>
            <Link href="/legal/privacy-policy" className="hover:underline">
              Gizlilik
            </Link>
            {" · "}
            <Link href="/legal/tos" className="hover:underline">
              Kullanım Şartları
            </Link>
            {" · "}
            <Link href="/legal/scraping-policy" className="hover:underline">
              Kaynak Politikası
            </Link>
          </p>
        </div>
      </footer>
    </div>
  );
}
