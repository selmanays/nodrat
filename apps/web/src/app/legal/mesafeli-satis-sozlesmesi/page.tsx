import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Mesafeli Satış Sözleşmesi — Nodrat",
  description:
    "TR Mesafeli Sözleşmeler Yönetmeliği uyumu — Lemon Squeezy MoR (Merchant of Record) ile satış akışı, 14 gün cayma hakkı, taraflar.",
};

export default function MesafeliSatisPage() {
  return (
    <main className="prose prose-slate dark:prose-invert mx-auto max-w-3xl px-4 py-10">
      <h1>Mesafeli Satış Sözleşmesi / Bilgilendirme</h1>

      <p>
        <strong>Sürüm:</strong> v0.1 · <strong>Son güncelleme:</strong>{" "}
        2026-05-08 · <strong>Durum:</strong> DRAFT (avukat final review)
      </p>

      <p>
        İşbu sayfa Türkiye Mesafeli Sözleşmeler Yönetmeliği uyarınca alıcıya
        yönelik bilgilendirme metnidir. Lemon Squeezy MoR yapısıyla satıcı
        sıfatı LS'de olsa dahi, TR Tüketici Kanunu kapsamında kullanıcıya
        yönelik bilgilendirme Nodrat tarafından erişilebilir tutulmaktadır.
      </p>

      <h2>1. Taraflar</h2>

      <h3>1.1 SATICI (Merchant of Record)</h3>
      <ul>
        <li>
          <strong>Unvan:</strong> Lemon Squeezy Inc.
        </li>
        <li>
          <strong>Tür:</strong> Delaware / ABD merkezli, MoR sıfatıyla
        </li>
        <li>
          <strong>E-posta:</strong>{" "}
          <a href="mailto:support@lemonsqueezy.com">support@lemonsqueezy.com</a>
        </li>
        <li>
          <strong>Web:</strong>{" "}
          <a
            href="https://lemonsqueezy.com"
            target="_blank"
            rel="noopener noreferrer"
          >
            lemonsqueezy.com
          </a>
        </li>
      </ul>

      <h3>1.2 HİZMET SAĞLAYICI (Yazılım Sağlayıcı, ürün sahibi)</h3>
      <ul>
        <li>
          <strong>Unvan:</strong> Nodrat — Selman Aytaş (şahıs ticari kazanç
          mükellefi)
        </li>
        <li>
          <strong>E-posta:</strong>{" "}
          <a href="mailto:support@nodrat.com">support@nodrat.com</a> (genel) /{" "}
          <a href="mailto:privacy@nodrat.com">privacy@nodrat.com</a> (KVKK)
        </li>
        <li>
          <strong>Web:</strong>{" "}
          <a href="https://nodrat.com">nodrat.com</a>
        </li>
      </ul>

      <h3>1.3 ALICI (Tüketici)</h3>
      <p>
        Hesap kayıtlı kullanıcı; Lemon Squeezy ödeme akışında bilgileri
        toplanan kişi.
      </p>

      <p className="rounded-lg border border-blue-300 bg-blue-50 p-4 text-sm text-blue-900 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200">
        <strong>MoR yapısı açıklaması:</strong> Lemon Squeezy,{" "}
        <strong>Merchant of Record (Resmi Satıcı)</strong> sıfatıyla Nodrat
        ürününün dijital hizmet satışını gerçekleştirir. LS, ödeme tahsilatı,
        fatura kesimi, KDV/VAT/sales tax compliance ve refund yönetiminden
        kendi adına ve kendi sorumluluğunda sorumludur. Nodrat ürün sahibi ve
        hizmet sağlayıcısıdır.
      </p>

      <h2>2. Sözleşmenin Konusu</h2>
      <p>
        İşbu sözleşme, ALICI'nın <code>https://nodrat.com</code> üzerinden
        yararlanacağı <strong>Nodrat dijital içerik üretim hizmeti</strong>{" "}
        aboneliğinin elektronik ortamda mesafeli satışına ilişkin TR Mesafeli
        Sözleşmeler Yönetmeliği uyarınca tarafların hak ve yükümlülüklerini
        düzenler.
      </p>

      <h2>3. Hizmet Bilgileri</h2>

      <h3>3.1 Tier yapısı (USD primary)</h3>
      <ul>
        <li>
          <strong>Free</strong>: ücretsiz, 10 üretim/ay
        </li>
        <li>
          <strong>Starter</strong>: $8/ay (~249 TL display ref) — 100 üretim/ay
        </li>
        <li>
          <strong>Pro</strong>: $24/ay (~749 TL) — 500 üretim/ay + Faz 5 stil
          profili
        </li>
        <li>
          <strong>Agency 3-seat</strong>: $79/ay (~2.499 TL) — 2.500 üretim/ay
          × 3 koltuk
        </li>
        <li>
          <strong>Agency 5-seat</strong>: $129/ay (~4.090 TL) — 5 koltuk
        </li>
        <li>
          <strong>Agency 10-seat</strong>: $249/ay (~7.890 TL) — 10 koltuk
        </li>
        <li>
          <strong>Yıllık:</strong> aylık fiyatın 10 katı (2 ay bedava, %16.7
          iskonto)
        </li>
      </ul>

      <h3>3.2 Ücret + vergi</h3>
      <ul>
        <li>
          <strong>Para birimi:</strong> USD primary (charge USD); TL display
          referans olarak gösterilir, fiili charge USD'dir.
        </li>
        <li>
          <strong>Vergi:</strong> KDV/VAT/sales tax fiyata dahildir. Lemon
          Squeezy MoR sıfatıyla müşteri lokasyonuna göre vergi keser ve
          faturada ayrı kalem olarak gösterir. TR müşteri için %20 KDV LS
          tarafından kesilir.
        </li>
        <li>
          <strong>FX:</strong> Kullanıcının bankası TL → USD dönüşümünü
          uygular; bazı TR bankaları yurt dışı kart işlemi için ek %1-3
          komisyon alabilir.
        </li>
      </ul>

      <h3>3.3 Ödeme yöntemi</h3>
      <p>
        Kredi kartı veya banka kartı (Visa, Mastercard, Amex). Ödeme tahsilatı
        Lemon Squeezy hosted checkout üzerinden gerçekleşir; kart bilgileri
        LS PCI-DSS Level 1 uyumluluğunda işlenir, Nodrat'a ulaşmaz.
      </p>

      <h2>4. Cayma Hakkı (TR Tüketici Kanunu m.48)</h2>

      <h3>4.1 Cayma süresi</h3>
      <ul>
        <li>
          <strong>Yıllık abonelik:</strong> 14 gün full refund hakkı
        </li>
        <li>
          <strong>Aylık abonelik:</strong> 14 gün cayma (kullanılmamış
          aboneliklerde iade)
        </li>
        <li>
          <strong>Beta / early adopter:</strong> 30 gün full refund (ticari
          garanti)
        </li>
      </ul>

      <h3>4.2 Cayma yöntemi</h3>
      <p>ALICI cayma hakkını şu yollarla kullanabilir:</p>
      <ol>
        <li>
          <strong>Lemon Squeezy Customer Portal</strong> (en hızlı):{" "}
          <a href="/app/billing/manage">/app/billing/manage</a> → "Aboneliği
          yönet"
        </li>
        <li>
          <strong>E-posta:</strong>{" "}
          <a href="mailto:support@lemonsqueezy.com">support@lemonsqueezy.com</a>{" "}
          (LS doğrudan)
        </li>
        <li>
          <strong>Nodrat aracılığıyla:</strong>{" "}
          <a href="mailto:support@nodrat.com">support@nodrat.com</a> (Nodrat
          LS'ye yönlendirir)
        </li>
      </ol>

      <p>
        İade işlemleri Lemon Squeezy MoR tarafından yürütülür. Onaylanan
        iadeler genellikle <strong>3-7 iş günü</strong> içinde kart hesabına
        yansır. Vergi (KDV/VAT) dahil tam iade yapılır.
      </p>

      <h3>4.3 Cayma hakkının kullanılamayacağı durumlar</h3>
      <p>
        Mesafeli Sözleşmeler Yönetmeliği m.15(1)(ğ) uyarınca dijital içeriğin
        elektronik ortamda anında ifa edildiği durumlarda cayma hakkının
        kullanılamaması mümkündür. Ancak Nodrat <strong>ticari garanti</strong>{" "}
        olarak 14 gün cayma hakkını tanır. Detay:{" "}
        <a href="/legal/refund-policy">İade Politikası</a>.
      </p>

      <h2>5. Yenilenme</h2>
      <ul>
        <li>Aylık abonelik: her ay otomatik yenilenir (LS renew)</li>
        <li>Yıllık abonelik: her yıl otomatik yenilenir</li>
        <li>İptal: dilediğiniz zaman LS Customer Portal'dan</li>
        <li>İptal sonrası: erişim mevcut dönem sonuna kadar devam eder</li>
      </ul>

      <h2>6. Şikayet ve Anlaşmazlık</h2>

      <h3>6.1 İletişim hiyerarşisi</h3>
      <ol>
        <li>
          <strong>support@lemonsqueezy.com</strong> — ödeme/fatura/refund (LS
          MoR sorumluluğu)
        </li>
        <li>
          <strong>support@nodrat.com</strong> — hizmet kalitesi, içerik üretim
          sorunları, hesap erişim
        </li>
        <li>
          <strong>privacy@nodrat.com</strong> — KVKK / kişisel veri başvuruları
        </li>
      </ol>

      <h3>6.2 Tüketici Hakem Heyeti / Mahkeme</h3>
      <p>TR tüketicisi olarak ALICI:</p>
      <ul>
        <li>
          <strong>Tüketici Hakem Heyeti</strong> (parasal limit altında):{" "}
          <a
            href="https://tuketicisikayet.tuketici.gov.tr"
            target="_blank"
            rel="noopener noreferrer"
          >
            tuketicisikayet.tuketici.gov.tr
          </a>
        </li>
        <li>
          <strong>Tüketici Mahkemesi</strong> (limit üstü)
        </li>
      </ul>

      <p>
        Yetkili mahkeme: İstanbul Mahkemeleri (Nodrat hizmet sağlayıcı yerleşim
        yeri) ya da ALICI'nın yerleşim yeri (TR Tüketici Kanunu m.73 uyarınca
        tüketici lehine).
      </p>

      <h2>7. Veri Koruma</h2>
      <p>
        Kişisel verilerin işlenmesi{" "}
        <a href="/legal/privacy">Gizlilik Politikası</a> ve{" "}
        <a href="/legal/kvkk-aydinlatma">KVKK Aydınlatma Metni</a> uyarınca
        yapılır. Lemon Squeezy MoR sıfatıyla ödeme verilerini ABD'de işler —
        KVKK m.9 yurt dışı transfer için ayrı açık rıza ödeme akışında alınır
        (server-side enforced).
      </p>

      <h2>8. Kabul Beyanı</h2>
      <p>
        ALICI, Lemon Squeezy hosted checkout'ta "Subscribe" / "Satın al"
        butonuna tıklayarak işbu Mesafeli Satış Sözleşmesi'nin tüm hükümlerini,{" "}
        <a href="/legal/tos">Hizmet Koşulları</a>,{" "}
        <a href="/legal/privacy">Gizlilik Politikası</a>,{" "}
        <a href="/legal/kvkk-aydinlatma">KVKK Aydınlatma Metni</a>,{" "}
        <a href="/legal/refund-policy">İade Politikası</a> ve{" "}
        <a href="/legal/cookies">Çerez Politikası</a>'nı okuduğunu, anladığını
        ve elektronik ortamda kabul ettiğini taahhüt eder.
      </p>
    </main>
  );
}
