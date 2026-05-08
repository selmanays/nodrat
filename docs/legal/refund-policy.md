# Nodrat — İade Politikası (Refund Policy)

**Doküman türü:** Legal — Refund Policy
**Sürüm:** v0.1 (2026-05-08, Epic [#448](https://github.com/selmanays/nodrat/issues/448))
**Durum:** DRAFT — avukat final review zorunlu (yayın öncesi)
**Bağımlılık:** ToS v0.2 §8, Pricing v0.2 §10, Compliance Brief v0.2

> **Avukat şartlı onayı (2026-05-08, Epic #448 review):** "LS hosted refund kullanmak operasyonel olarak uygun. Ancak Türkiye'de tüketiciye dönük SaaS satışında yalnızca 'LS portal refund yönetir' demek yetmez." Bu sayfa Nodrat tarafında yayında olmalı; ayrıca pricing ekranında "İlk 14 gün iade" ibaresi + billing ekranında "İade işlemleri Lemon Squeezy üzerinden yürütülür" açıklaması zorunlu.

---

## 1. Genel İlke — 14 gün cayma hakkı

```text
Yıllık abonelik: Satın alma sonrası 14 gün içinde tam iade hakkı (full refund)
Aylık abonelik: 14 gün cayma — kullanılmamış aboneliklerde iade
Beta/early adopter: 30 gün full refund (güven inşası)
Free tier: ücret yok, iade konusu yok
```

Bu süre **Türkiye Mesafeli Sözleşmeler Yönetmeliği** (TR e-ticaret hukuku) + **AB tüketici cooling-off period** ile uyumlu olarak tanımlanmıştır. Dijital hizmetlerde cayma hakkının istisnaları olabilir; Nodrat **ticari garanti olarak** 14 gün iadeyi benimser (kullanıcı dostu pozisyon).

---

## 2. Kim, Nasıl Talep Eder?

İade talebi **Lemon Squeezy Customer Portal** üzerinden veya `support@lemonsqueezy.com` adresine gönderilir. LS bizim için **Merchant of Record (MoR)** olarak çalışır — yani satıcı LS'dir, fatura LS keser, refund LS işler.

**3 yol:**

1. **Self-service (önerilen):** [`/app/billing/manage`](https://nodrat.com/app/billing/manage) → "Aboneliği yönet" → Lemon Squeezy hosted Customer Portal → "Cancel & Request Refund"
2. **Email:** support@lemonsqueezy.com (LS doğrudan iletişim)
3. **Nodrat support:** support@nodrat.com — Nodrat ekibi LS'ye yönlendirir; LS hosted refund flow zorunlu

> **Önemli:** Nodrat doğrudan refund işleyemez. LS MoR sıfatıyla ödemeyi alıyor, LS işliyor. Talep alındığında genellikle **3-7 iş günü** içinde kart hesabına yansır.

---

## 3. Aylık vs Yıllık — detay

### 3.1 Aylık abonelik

```text
- Cayma süresi: 14 gün (satın alma + her yenileme dahil değil — sadece ilk satın alma)
- Kullanılmış ay: iade yok (kanun uyarınca dijital hizmet kullanımı)
- Sonraki yenileme öncesi iptal: erişim ay sonuna kadar devam eder
- LS Smart Retry (3-7 gün): ödeme başarısız olursa LS otomatik retry → grace 7 gün → Free downgrade
```

### 3.2 Yıllık abonelik

```text
- Cayma süresi: 14 gün — TAM İADE (LS otomatik prorate refund hesaplar)
- 14 günden sonra: iade yok, ay sonu / dönem sonu iptal
- Yıllık → aylık downgrade: Faz 7+ değerlendirilir (Pricing §5.3)
```

### 3.3 Beta/early adopter

```text
- 30 gün full refund (lifetime "founding member" pricing alanlar)
- Talep email ile (30 gün sonra normal kural)
```

---

## 4. Hangi Durumlarda İade Yapılmaz?

```text
- 14 gün geçtikten sonra (yıllık dahil)
- Aylık abonelikte kullanılmış ay
- ToS ihlali nedeniyle iptal edilen hesaplar (FSEK 25-kelime cap, scraping policy ihlali, abuse)
- Free tier (ücret yok)
- Lifetime / founding member offers (30 gün geçince — yukarıdaki istisna dışında)
```

**ToS ihlali iptali** durumunda hizmet derhal sonlandırılır ve **iade yapılmaz**; bu durumlar [Hizmet Koşulları](tos.md) §5'te detaylandırılmıştır.

---

## 5. Vergi ve Fatura

LS müşteriye fatura keser (KDV/VAT/sales tax dahil) ve iade onaylandığında **vergi dahil tam iade** yapılır. Nodrat e-Arşiv kesmez; LS hosted invoice + LS hosted refund receipt yeterlidir (Epic #448, [Lemon Squeezy MoR locked decision](../../wiki/decisions/lemon-squeezy-payment-provider.md)).

**Önemli:** Refund onaylandığında LS payout'undan düşülür (Nodrat hesabından LS net revenue azaltılır). Chargeback fee (~$15-20 LS standart) kullanıcıya yansıtılmaz; bu Nodrat operasyonel maliyetidir.

---

## 6. Anlaşmazlık (Dispute) Akışı

LS hosted refund sürecinde itiraz/anlaşmazlık olursa:

1. **İlk basamak:** support@lemonsqueezy.com (LS resolution)
2. **İkinci basamak:** support@nodrat.com (Nodrat müdahalesi — sadece bilgi/iletişim)
3. **Üçüncü basamak (TR kullanıcı):** [Tüketici Hakem Heyeti](https://tuketicisikayet.tuketici.gov.tr) (TR Tüketici Kanunu kapsamında)

> **Yargı yetkisi:** Lemon Squeezy Inc. ABD Delaware merkezli; ödeme/refund anlaşmazlıkları öncelikle LS ToS uyarınca çözülür. Nodrat Hizmet Koşulları gereği ek olarak [İstanbul mahkemeleri](tos.md) yetkilidir.

---

## 7. Fiyat Değişikliği ve İade

Nodrat fiyatları 30 gün önceden bildirimle değiştirebilir. Değişiklik **mevcut yıllık aboneler için dönemin sonuna kadar uygulanmaz**. Yıllık aboneler fiyat artışından korunur.

Aylık abonelerin yenileme tarihinde yeni fiyat uygulanır; bu durumda kullanıcı yenileme öncesinde iptal edebilir.

---

## 8. İlişkili Dokümanlar

- [Hizmet Koşulları (ToS)](tos.md) §8 — Faturalama ve İade
- [Mesafeli Satış Sözleşmesi](mesafeli-satis-sozlesmesi.md) — TR Mesafeli Sözleşmeler Yönetmeliği uyumu
- [Gizlilik Politikası](privacy-policy.md) §4 — LS data processor (ABD)
- [KVKK Aydınlatma Metni](kvkk-aydinlatma.md) §3 — yurt dışı transfer açık rıza

---

**Son güncelleme:** 2026-05-08
**Yayın durumu:** DRAFT — avukat final review bekliyor (Epic #448 launch öncesi)
**İletişim:** privacy@nodrat.com (KVKK), support@nodrat.com (genel), support@lemonsqueezy.com (refund)
