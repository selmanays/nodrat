/**
 * /bot — NodratBot transparency landing
 *
 * Yayıncılar için "Bu botu nasıl tanıyacağım, nasıl engelleyeceğim?"
 * sorusunun açık cevabı.
 *
 * docs/legal/scraping-policy.md §2
 * docs/legal/opinion-integration.md §3.3
 *
 * Robots.txt'de ve HTTP header'larda kullanılan canonical URL: https://nodrat.com/bot
 */

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "NodratBot — Yayıncılar için bilgi | Nodrat",
  description:
    "NodratBot kim, ne yapar ve sitenizden veri toplamasını nasıl engellersiniz?",
  // Pre-launch noindex layout.tsx'te global; /bot publik olduğu için açık tutulabilir,
  // ama MVP-1 öncesi hâlâ noindex tercih ediyoruz.
};

const NODRAT_UA =
  "NodratBot/1.0 (+https://nodrat.com/bot; contact: legal@nodrat.com)";

export default function BotInfoPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 md:px-6 py-16 prose prose-slate dark:prose-invert">
      <header className="not-prose mb-10">
        <p className="text-sm text-muted-foreground">Yayıncılar için bilgi</p>
        <h1 className="text-4xl font-semibold tracking-tight text-foreground ">
          NodratBot
        </h1>
        <p className="mt-3 text-lg text-muted-foreground">
          Türkçe haber ekosistemini taradığımız HTTP istemcimizin kimliği.
        </p>
      </header>

      <section>
        <h2>Kim?</h2>
        <p>
          <strong>NodratBot</strong>, Nodrat platformuna ait, kamuya açık
          haberleri taramak için kullanılan istemcimizdir. Tüm istekler
          aşağıdaki sabit User-Agent ile gider:
        </p>
        <pre className="text-xs">{NODRAT_UA}</pre>
        <p>
          Ek olarak <code>From: legal@nodrat.com</code> ve{" "}
          <code>Accept-Language: tr-TR,tr;q=0.9,en;q=0.5</code> header'ları
          gönderilir. Şüpheli bir User-Agent görürseniz bizimle iletişime
          geçin: <a href="mailto:legal@nodrat.com">legal@nodrat.com</a>.
        </p>
      </section>

      <section>
        <h2>Ne yapar, ne yapmaz?</h2>
        <ul>
          <li>
            <strong>Yapar:</strong> Yalnızca <em>kamuya açık</em> haber sayfalarını
            indirir; başlık, gövde metni, yayın zamanı, yazar bilgilerini
            çıkarır.
          </li>
          <li>
            <strong>Yapmaz:</strong> Ücretli (paywall) içeriklere, login
            arkasındaki sayfalara, CAPTCHA'lı korumalara ve robots.txt ile
            yasaklanmış path'lere <strong>kategorik olarak</strong> erişim
            denemez.
          </li>
          <li>
            <strong>Saklamaz:</strong> Site sahibi tarafından paylaşılmamış
            kişisel veriyi saklamaz; yorum, e-posta, telefon gibi PII
            otomatik redact edilir.
          </li>
        </ul>
      </section>

      <section>
        <h2>Nodrat'ı nasıl engellersiniz?</h2>
        <p>
          Üç farklı yöntemden herhangi birini kullanabilirsiniz; tümüne
          tamamen uyarız.
        </p>

        <h3>1) robots.txt (önerilen)</h3>
        <pre>{`User-agent: NodratBot
Disallow: /`}</pre>
        <p>
          Bu kural eklendikten sonra mevcut taramalar bir sonraki turda
          durdurulur ve siteniz kaynak listemizden çıkarılır. Daha sınırlı
          engelleme için belirli path'leri Disallow olarak ekleyebilirsiniz.
        </p>

        <h3>2) HTTP 403 / 429</h3>
        <p>
          Sunucunuz NodratBot User-Agent'ından gelen isteklere 403 veya 429
          dönerse 5 ardışık başarısızlık sonrası kaynak otomatik
          durdurulur. Manuel engellemeden daha hızlı sonuç verir.
        </p>

        <h3>3) Doğrudan talep (manuel kaldırma)</h3>
        <p>
          Sitenizin tamamı veya bir bölümü için manuel kaldırma talebinizi{" "}
          <a href="/legal/abuse">abuse formu</a>'ndan iletebilirsiniz.
          Yanıt süremiz en fazla 7 iş günüdür.
        </p>
      </section>

      <section>
        <h2>Erişim sıklığımız</h2>
        <ul>
          <li>Kaynak başına maksimum: 10 istek / dakika (varsayılan)</li>
          <li>Eş zamanlı bağlantı: 1</li>
          <li>
            <code>Crawl-delay</code> direktifi varsa kuralınıza uyarız.
          </li>
          <li>
            HTTP 429 veya art arda 5 hatadan sonra otomatik
            <em> exponential backoff</em>.
          </li>
        </ul>
      </section>

      <section>
        <h2>İletişim</h2>
        <p>
          Soru, şikâyet veya iş birliği için:{" "}
          <a href="mailto:legal@nodrat.com">legal@nodrat.com</a>. Yasal
          süreçler için:{" "}
          <a href="/legal/abuse">/legal/abuse</a>,{" "}
          <a href="/legal/takedown">/legal/takedown</a>,{" "}
          <a href="/legal/copyright">/legal/copyright</a>.
        </p>
      </section>

      <footer className="mt-12 border-t pt-6 text-sm text-muted-foreground">
        Son güncelleme: Mayıs 2026 — Nodrat MVP-1 hazırlık dönemi.
      </footer>
    </main>
  );
}
