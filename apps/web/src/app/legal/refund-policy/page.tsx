import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "İade Politikası — Nodrat",
  description:
    "Nodrat abonelik iade politikası. 14 gün cayma hakkı, Lemon Squeezy hosted refund flow, aylık/yıllık detay.",
};

export default function RefundPolicyPage() {
  return (
    <main className="prose prose-slate dark:prose-invert mx-auto max-w-3xl px-4 py-10">
      <h1>İade Politikası</h1>

      <p>
        <strong>Sürüm:</strong> v0.1 · <strong>Son güncelleme:</strong>{" "}
        2026-05-08 · <strong>Durum:</strong> DRAFT (avukat final review)
      </p>

      <p>
        İşbu sayfa Nodrat abonelik iade politikasını anlatır. Ödeme tahsilatı{" "}
        <strong>Lemon Squeezy Inc.</strong> (Stripe Atlas iştiraki, ABD merkezli){" "}
        <strong>Merchant of Record (MoR)</strong> sıfatıyla yapıldığı için
        iade işlemleri Lemon Squeezy hosted refund flow üzerinden yürütülür.
      </p>

      <h2>1. Genel ilke — 14 gün cayma hakkı</h2>
      <ul>
        <li>
          <strong>Yıllık abonelik:</strong> satın alma sonrası 14 gün içinde
          tam iade hakkı (full refund). Lemon Squeezy otomatik prorate refund
          hesaplar.
        </li>
        <li>
          <strong>Aylık abonelik:</strong> 14 gün cayma hakkı kullanılmamış
          aboneliklerde geçerlidir. Kullanılmış ay için iade yapılmaz (kanun
          uyarınca dijital hizmet kullanımı).
        </li>
        <li>
          <strong>Beta / early adopter:</strong> 30 gün full refund (ticari
          garanti, lifetime "founding member" kapsamı).
        </li>
        <li>
          <strong>Free tier:</strong> ücret yok, iade konusu yok.
        </li>
      </ul>

      <p>
        Bu süre <strong>Türkiye Mesafeli Sözleşmeler Yönetmeliği</strong> + AB
        cooling-off period ile uyumlu olarak tanımlanmıştır. Dijital
        hizmetlerde cayma hakkının istisnaları olabilir; Nodrat ticari garanti
        olarak 14 gün iadeyi benimser (kullanıcı dostu pozisyon).
      </p>

      <h2>2. Talep yolları</h2>
      <p>
        İade talebi <strong>3 yoldan</strong> başlatılabilir:
      </p>
      <ol>
        <li>
          <strong>Self-service (önerilen):</strong>{" "}
          <a href="/app/billing/manage">Aboneliği yönet</a> → Lemon Squeezy
          hosted Customer Portal → "Cancel & Request Refund"
        </li>
        <li>
          <strong>E-posta:</strong>{" "}
          <a href="mailto:support@lemonsqueezy.com">support@lemonsqueezy.com</a>{" "}
          (LS doğrudan iletişim)
        </li>
        <li>
          <strong>Nodrat support:</strong>{" "}
          <a href="mailto:support@nodrat.com">support@nodrat.com</a> — Nodrat
          ekibi LS'ye yönlendirir; iade işlemi LS hosted flow üzerinden
          tamamlanır.
        </li>
      </ol>

      <p className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
        <strong>Önemli:</strong> Nodrat doğrudan refund işleyemez. Lemon
        Squeezy MoR sıfatıyla ödemeyi alır ve iadeyi işler. Talep alındığında
        genellikle <strong>3-7 iş günü</strong> içinde kart hesabına yansır.
      </p>

      <h2>3. Aylık vs yıllık detay</h2>
      <h3>3.1 Aylık abonelik</h3>
      <ul>
        <li>Cayma süresi: 14 gün (sadece ilk satın alma — yenilemeler dahil değil)</li>
        <li>Kullanılmış ay: iade yok</li>
        <li>Sonraki yenileme öncesi iptal: erişim ay sonuna kadar devam eder</li>
        <li>
          LS Smart Retry (3-7 gün): ödeme başarısız → otomatik retry → grace
          7 gün → Free downgrade
        </li>
      </ul>

      <h3>3.2 Yıllık abonelik</h3>
      <ul>
        <li>Cayma süresi: 14 gün — TAM İADE (LS otomatik prorate hesaplar)</li>
        <li>14 günden sonra: iade yok, dönem sonu iptal</li>
      </ul>

      <h3>3.3 Beta / early adopter</h3>
      <ul>
        <li>30 gün full refund (lifetime "founding member" pricing kapsamı)</li>
        <li>Talep e-posta ile (30 gün sonra normal kural)</li>
      </ul>

      <h2>4. Hangi durumlarda iade yapılmaz?</h2>
      <ul>
        <li>14 gün geçtikten sonra (yıllık dahil)</li>
        <li>Aylık abonelikte kullanılmış ay (kanun uyarınca)</li>
        <li>
          Hizmet Koşulları ihlali nedeniyle iptal edilen hesaplar (FSEK 25
          kelime cap ihlali, scraping policy ihlali, abuse)
        </li>
        <li>Free tier (ücret yok)</li>
        <li>Lifetime / founding member offers (30 gün geçince)</li>
      </ul>

      <p>
        Hizmet Koşulları ihlali iptali durumunda hizmet derhal sonlandırılır
        ve iade yapılmaz; bu durumlar{" "}
        <a href="/legal/tos">Hizmet Koşulları</a> §5'te detaylandırılmıştır.
      </p>

      <h2>5. Vergi ve fatura</h2>
      <p>
        Lemon Squeezy müşteriye fatura keser (KDV/VAT/sales tax dahil) ve iade
        onaylandığında <strong>vergi dahil tam iade</strong> yapılır. Nodrat
        ayrıca e-Arşiv kesmez; LS hosted invoice + LS hosted refund receipt
        yeterlidir.
      </p>

      <h2>6. Anlaşmazlık akışı</h2>
      <p>LS hosted refund sürecinde itiraz/anlaşmazlık olursa:</p>
      <ol>
        <li>
          <strong>İlk basamak:</strong>{" "}
          <a href="mailto:support@lemonsqueezy.com">support@lemonsqueezy.com</a>{" "}
          (LS resolution)
        </li>
        <li>
          <strong>İkinci basamak:</strong>{" "}
          <a href="mailto:support@nodrat.com">support@nodrat.com</a> (Nodrat
          müdahalesi — bilgi/iletişim)
        </li>
        <li>
          <strong>Üçüncü basamak (TR kullanıcı):</strong>{" "}
          <a
            href="https://tuketicisikayet.tuketici.gov.tr"
            target="_blank"
            rel="noopener noreferrer"
          >
            Tüketici Hakem Heyeti
          </a>
        </li>
      </ol>

      <h2>7. Fiyat değişikliği ve iade</h2>
      <p>
        Nodrat fiyatları 30 gün önceden bildirimle değiştirebilir. Değişiklik
        mevcut yıllık aboneler için dönemin sonuna kadar uygulanmaz. Aylık
        abonelerin yenileme tarihinde yeni fiyat uygulanır; bu durumda
        kullanıcı yenileme öncesinde iptal edebilir.
      </p>

      <h2>İlişkili dokümanlar</h2>
      <ul>
        <li>
          <a href="/legal/tos">Hizmet Koşulları</a> §8 — Faturalama ve İade
        </li>
        <li>
          <a href="/legal/mesafeli-satis-sozlesmesi">
            Mesafeli Satış Sözleşmesi
          </a>{" "}
          — TR Mesafeli Sözleşmeler Yönetmeliği uyumu
        </li>
        <li>
          <a href="/legal/privacy">Gizlilik Politikası</a> §4 — LS data
          processor (ABD)
        </li>
        <li>
          <a href="/legal/kvkk-aydinlatma">KVKK Aydınlatma Metni</a> §3 — yurt
          dışı transfer açık rıza
        </li>
      </ul>

      <p className="text-sm text-slate-500">
        İletişim:{" "}
        <a href="mailto:support@nodrat.com">support@nodrat.com</a> (genel) ·{" "}
        <a href="mailto:support@lemonsqueezy.com">support@lemonsqueezy.com</a>{" "}
        (refund) ·{" "}
        <a href="mailto:privacy@nodrat.com">privacy@nodrat.com</a> (KVKK)
      </p>
    </main>
  );
}
