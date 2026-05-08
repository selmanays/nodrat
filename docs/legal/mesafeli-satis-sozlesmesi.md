# Nodrat — Mesafeli Satış Sözleşmesi / Bilgilendirme

**Doküman türü:** Legal — Mesafeli Satış Bilgilendirmesi (TR Mesafeli Sözleşmeler Yönetmeliği uyumu)
**Sürüm:** v0.1 (2026-05-08, Epic [#448](https://github.com/selmanays/nodrat/issues/448))
**Durum:** DRAFT — avukat final review zorunlu (yayın öncesi)
**Bağımlılık:** ToS v0.2, Refund Policy v0.1, Compliance Brief v0.2

> **Avukat şartlı onayı (2026-05-08, Epic #448 review):** Lemon Squeezy MoR yapısıyla LS'nin satıcı sıfatıyla işlem yaptığı durumda dahi, **TR Tüketici Kanunu kapsamında** kullanıcıya yönelik bilgilendirme ve mesafeli satış akışı Nodrat tarafında erişilebilir olmalı. Bu sayfa Nodrat sitesinde yayında, satın alma akışında footer veya checkout sayfasından link ile ulaşılabilir olmalıdır.

---

## 1. Taraflar

```text
SATICI (Merchant of Record)
  Unvan       : Lemon Squeezy Inc.
  Tür         : Delaware / ABD merkezli, MoR sıfatıyla
  E-posta     : support@lemonsqueezy.com
  Web         : https://lemonsqueezy.com

HİZMET SAĞLAYICI (Yazılım Sağlayıcı, ürün sahibi)
  Unvan       : Nodrat — Selman Aytaş (şahıs ticari kazanç mükellefi — vergi danışmanı önerisi)
  E-posta     : support@nodrat.com (genel) / privacy@nodrat.com (KVKK)
  Web         : https://nodrat.com

ALICI (Tüketici)
  Hesap kayıtlı kullanıcı; Lemon Squeezy ödeme akışında bilgileri toplanan kişi
```

> **Önemli — MoR yapısı açıklaması:** Lemon Squeezy, **Merchant of Record (Resmi Satıcı)** sıfatıyla Nodrat ürününün dijital hizmet satışını gerçekleştirir. LS, ödeme tahsilatı, fatura kesimi, KDV/VAT/sales tax compliance ve refund yönetiminden **kendi adına ve kendi sorumluluğunda** sorumludur. Nodrat ürün sahibi ve hizmet sağlayıcısıdır; LS payout aldıktan sonra geliri muhasebeleştirir.

---

## 2. Sözleşmenin Konusu

İşbu sözleşme, ALICI'nın `https://nodrat.com` üzerinden yararlanacağı **Nodrat dijital içerik üretim hizmeti aboneliği**'nin elektronik ortamda mesafeli satışına ilişkin TR Mesafeli Sözleşmeler Yönetmeliği uyarınca tarafların hak ve yükümlülüklerini düzenler.

---

## 3. Hizmet Bilgileri

### 3.1 Tier yapısı (USD primary, TL display referans)

```text
Free          : ücretsiz, 10 üretim/ay
Starter       : $8/ay (~249 TL anlık FX)   — 100 üretim/ay
Pro           : $24/ay (~749 TL)           — 500 üretim/ay + Faz 5 stil profili
Agency 3-seat : $79/ay (~2.499 TL)         — 2.500 üretim/ay × 3 koltuk
Agency 5-seat : $129/ay (~4.090 TL)        — 2.500 üretim/ay × 5 koltuk
Agency 10-seat: $249/ay (~7.890 TL)        — 2.500 üretim/ay × 10 koltuk
Yıllık        : aylık fiyatın 10 katı (2 ay bedava, %16.7 iskonto)
```

### 3.2 Ücret + vergi

- **Para birimi:** USD primary (charge USD); TL display **anlık döviz kuru ile referans** olarak gösterilir, fiili charge USD'dir.
- **Vergi:** KDV/VAT/sales tax fiyata dahildir. Lemon Squeezy MoR sıfatıyla müşteri lokasyonuna göre vergi keser ve faturada ayrı kalem olarak gösterir. **TR müşteri için %20 KDV** LS tarafından kesilir.
- **FX:** Kullanıcının bankası TL → USD dönüşümünü uygular; bazı TR bankaları yurt dışı kart işlemi için ek %1-3 komisyon alabilir.

### 3.3 Ödeme yöntemi

Kredi kartı veya banka kartı (Visa, Mastercard, Amex). Ödeme tahsilatı **Lemon Squeezy hosted checkout** üzerinden gerçekleşir; kart bilgileri LS PCI-DSS Level 1 uyumluluğunda işlenir, **Nodrat'a ulaşmaz**.

---

## 4. Cayma Hakkı (TR Tüketici Kanunu m.48 + Mesafeli Sözleşmeler Yönetmeliği m.15)

### 4.1 Cayma süresi

```text
Yıllık abonelik: 14 gün full refund hakkı
Aylık abonelik: 14 gün cayma (kullanılmamış aboneliklerde iade)
Beta/early adopter: 30 gün full refund (ticari garanti)
```

### 4.2 Cayma yöntemi

ALICI cayma hakkını şu yollarla kullanabilir:

1. **Lemon Squeezy Customer Portal** (en hızlı): [`/app/billing/manage`](https://nodrat.com/app/billing/manage) → "Aboneliği yönet"
2. **E-posta:** support@lemonsqueezy.com (LS doğrudan)
3. **Nodrat aracılığıyla:** support@nodrat.com (Nodrat LS'ye yönlendirir)

İade işlemleri **Lemon Squeezy MoR** tarafından yürütülür. Onaylanan iadeler genellikle **3-7 iş günü** içinde kart hesabına yansır. Vergi (KDV/VAT) dahil tam iade yapılır.

### 4.3 Cayma hakkının kullanılamayacağı durumlar

Mesafeli Sözleşmeler Yönetmeliği m.15(1)(ğ) uyarınca **dijital içeriğin elektronik ortamda anında ifa edildiği** durumlarda cayma hakkının kullanılamaması mümkündür. Ancak Nodrat **ticari garanti olarak** 14 gün cayma hakkını tanır. Bu, kanunda öngörülen minimum üzerinde tüketici dostu bir taahhüttür.

**İstisnalar (cayma hakkı yok):**
- 14 gün geçtikten sonra (yıllık dahil)
- Aylık abonelikte kullanılmış ay (kanun uyarınca)
- ToS ihlali nedeniyle iptal edilen hesaplar (FSEK 25-kelime cap ihlali, scraping policy ihlali, abuse)
- Free tier (ücret yok, cayma konusu yok)

Detay: [İade Politikası (Refund Policy)](refund-policy.md).

---

## 5. Yenilenme

```text
Aylık abonelik: her ay otomatik yenilenir (Lemon Squeezy renew)
Yıllık abonelik: her yıl otomatik yenilenir
İptal: dilediğiniz zaman LS Customer Portal'dan
İptal sonrası: erişim mevcut dönem sonuna kadar devam eder (anında değil)
```

Fiyat değişikliği yapılırsa **30 gün önceden e-posta ile bildirilir**; mevcut yıllık aboneler dönem sonuna kadar eski fiyattan yararlanır.

---

## 6. Şikayet ve Anlaşmazlık

### 6.1 İletişim hiyerarşisi

1. **support@lemonsqueezy.com** — ödeme/fatura/refund (LS MoR sorumluluğu)
2. **support@nodrat.com** — hizmet kalitesi, içerik üretim sorunları, hesap erişim
3. **privacy@nodrat.com** — KVKK / kişisel veri başvuruları

### 6.2 Tüketici Hakem Heyeti / Mahkeme

TR tüketicisi olarak ALICI:

- **Tüketici Hakem Heyeti** (parasal limit: 2026 yılı için 5.500 TL'ye kadar): https://tuketicisikayet.tuketici.gov.tr
- **Tüketici Mahkemesi** (limit üstü)

Yetkili mahkeme: **İstanbul Mahkemeleri** (Nodrat hizmet sağlayıcı yerleşim yeri) ya da ALICI'nın yerleşim yeri (TR Tüketici Kanunu m.73 uyarınca tüketici lehine).

LS MoR yapısı dolayısıyla ödeme/fatura konuları öncelikle Lemon Squeezy ToS uyarınca çözülür (Delaware, ABD).

---

## 7. Veri Koruma

Kişisel verilerin işlenmesi [Gizlilik Politikası](privacy-policy.md) ve [KVKK Aydınlatma Metni](kvkk-aydinlatma.md) uyarınca yapılır. Lemon Squeezy MoR sıfatıyla ödeme verilerini ABD'de işler — KVKK m.9 yurt dışı transfer için **ayrı açık rıza** ödeme akışında alınır (server-side enforced).

---

## 8. Kabul Beyanı

ALICI, Lemon Squeezy hosted checkout'ta "Satın al" / "Subscribe" butonuna tıklayarak işbu Mesafeli Satış Sözleşmesi'nin tüm hükümlerini, [Hizmet Koşulları](tos.md), [Gizlilik Politikası](privacy-policy.md), [KVKK Aydınlatma Metni](kvkk-aydinlatma.md), [İade Politikası](refund-policy.md) ve [Çerez Politikası](cookies-policy.md)'nı okuduğunu, anladığını ve elektronik ortamda kabul ettiğini taahhüt eder.

---

**Son güncelleme:** 2026-05-08
**Yayın durumu:** DRAFT — avukat final review bekliyor (Epic #448 launch öncesi)
**İlişkili dokümanlar:** [ToS](tos.md), [Refund Policy](refund-policy.md), [Privacy Policy](privacy-policy.md), [KVKK Aydınlatma](kvkk-aydinlatma.md)
