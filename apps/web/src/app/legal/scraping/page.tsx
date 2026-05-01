export const metadata = {
  title: "Tarama Politikası | Nodrat",
};

export default function ScrapingPage() {
  return (
    <div>
      <h1>Tarama Politikası — Yayıncılar İçin</h1>
      <p className="text-sm text-muted-foreground">
        Son güncelleme: 2 Mayıs 2026 (taslak v1.0). Detaylı bilgi:{" "}
        <a href="/bot">/bot</a>.
      </p>

      <h2>NodratBot kim?</h2>
      <p>
        NodratBot, Nodrat platformuna ait, kamuya açık Türkçe haberleri taramak
        için kullanılan HTTP istemcimizdir. Tüm istekler aşağıdaki sabit
        User-Agent ile gider:
      </p>
      <pre>NodratBot/1.0 (+https://nodrat.com/bot; contact: legal@nodrat.com)</pre>

      <h2>Etik kurallarımız</h2>
      <ol>
        <li>
          <strong>robots.txt zero-tolerance:</strong> Disallow path'ler
          kategorik olarak taranmaz (admin override yok).
        </li>
        <li>
          <strong>Paywall hard ban:</strong> Ücretli içerik, login arkası,
          CAPTCHA'lı korumalar hiçbir zaman taranmaz.
        </li>
        <li>
          <strong>Rate limit:</strong> Kaynak başına 10 istek/dakika, 1 eş
          zamanlı bağlantı, Crawl-delay direktifi varsa uygulanır.
        </li>
        <li>
          <strong>Backoff:</strong> HTTP 429 veya art arda 5 hata sonrası
          exponential backoff + auto-deactivate.
        </li>
        <li>
          <strong>Tam metin saklama:</strong> Tam haber metni internal RAG
          katmanında saklanır;{" "}
          <strong>son kullanıcıya gösterilmez</strong>. Sadece özet, ana noktalar
          ve kaynak referansı sunulur.
        </li>
        <li>
          <strong>FSEK uyumu:</strong> Direct quote 25 kelimeyi aşmaz.
        </li>
        <li>
          <strong>PII redaction:</strong> Yorum/email/telefon/IBAN/TC pattern'leri
          otomatik redact edilir.
        </li>
      </ol>

      <h2>Engelleme yöntemleri</h2>

      <h3>1. robots.txt (önerilen)</h3>
      <pre>{`User-agent: NodratBot
Disallow: /`}</pre>
      <p>
        Bu kural eklendikten sonra mevcut taramalar sonraki turda durdurulur,
        siteniz kaynak listemizden çıkarılır.
      </p>

      <h3>2. HTTP 403 / 429</h3>
      <p>
        NodratBot User-Agent'ından gelen isteklere 403/429 dönerseniz 5 ardışık
        başarısızlık sonrası kaynak otomatik durdurulur.
      </p>

      <h3>3. Doğrudan talep</h3>
      <p>
        Manuel kaldırma için <a href="/legal/abuse">/legal/abuse</a> formunu
        kullanabilirsiniz. Yanıt süresi 24 saat triaj + 7 iş günü resolve.
      </p>

      <h2>Yayıncı hakları</h2>
      <ul>
        <li>İçeriğinizin tarama listemizden çıkarılmasını talep etme hakkı</li>
        <li>FSEK kapsamında telif şikayeti (
          <a href="/legal/copyright">/legal/copyright</a>)
        </li>
        <li>5651 kapsamında kişilik haklarını koruma (
          <a href="/legal/takedown">/legal/takedown</a>)
        </li>
        <li>İletişim: <a href="mailto:legal@nodrat.com">legal@nodrat.com</a></li>
      </ul>

      <h2>Şeffaflık</h2>
      <p>
        Hangi kaynaklardan içerik aldığımız admin panelimizde audit log'a
        yazılır. Bu liste talep üzerine yayıncılarla paylaşılır.
      </p>
    </div>
  );
}
