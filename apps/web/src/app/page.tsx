import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Logo } from "@/components/brand/logo";

/**
 * Landing page — Faz 0+ MVP-1.
 *
 * Pre-launch noindex (layout.tsx). Landing daha sonra genişletilir.
 * docs/design/ux-wireframes.md §6 (TOFU)
 */

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-6">
      <div className="max-w-2xl text-center space-y-8">
        <div className="inline-block rounded-full bg-accent-100 px-3 py-1 text-xs font-medium text-accent-900">
          MVP-1 — Hazırlık
        </div>

        <h1 className="flex justify-center">
          <Logo variant="wordmark" size="lg" className="h-16 w-auto sm:h-20" />
          <span className="sr-only">Nodrat</span>
        </h1>

        <p className="text-xl text-muted-foreground">
          Gündemi kaynaklı X içeriklerine dönüştüren{" "}
          <span className="font-medium text-foreground">
            editör odaklı üretim aracı
          </span>
          .
        </p>

        <p className="text-base text-muted-foreground max-w-xl mx-auto">
          ChatGPT&apos;nin yanında, gündem için özel araç. Kaynaklı çıktı, halüsinasyon koruması,
          PII redaction. Türkçe haber için tasarlandı.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
          <Button asChild size="lg" variant="accent">
            <Link href="/register">Kayıt ol</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/login">Giriş yap</Link>
          </Button>
        </div>

        <p className="text-xs text-muted-foreground pt-4">
          <Link
            href="/bot"
            className="hover:text-foreground hover:underline"
          >
            Yayıncılar için NodratBot bilgisi
          </Link>
        </p>
      </div>
    </main>
  );
}
