# Nodrat — Payment Provider Fallback Plan (R-FIN-04)

**Doküman türü:** Operational — Payment Provider Risk Mitigation Plan
**Sürüm:** v0.1 (2026-05-08, Epic [#448](https://github.com/selmanays/nodrat/issues/448))
**Bağımlılık:** Risk Register v0.3 R-FIN-04, [Lemon Squeezy locked decision](../../wiki/decisions/lemon-squeezy-payment-provider.md)
**Risk:** R-FIN-04 — LS MoR account closure / payout delay (skor 9 🔴)

> **Avukat görüşü (Epic #448 review):** "LS account closure / payout delay (R-FIN-04) için fallback plan **kesinlikle gereklidir**. Launch öncesi en azından 'Paddle fallback checklist' hazır olmalı." Bu doküman 6-senaryo aksiyon matrisi + Paddle ön başvuru durumu + provider abstraction kontrolü içerir.

---

## 1. Risk Tanımı (R-FIN-04)

```text
Risk : Lemon Squeezy MoR account closure / payout delay
Skor : 9 🔴 (olasılık 3 × etki 3)
Etki : Yeni abonelik kabul edilemez, mevcut payout'lar gecikir,
       en kötü senaryoda hesap kapanır → tüm checkout/portal devre dışı
Sebep: LS policy violation (false positive), banking issue,
       fraud signal, account review (manuel inceleme),
       country geo-restriction
```

LS MoR yapısı tek bir provider'a operasyonel bağımlılık yaratır — bu R-FIN-04'ün özü. Mitigation: ikinci MoR provider (Paddle) için ön hazırlık.

---

## 2. 6-Senaryo Aksiyon Matrisi (avukat onaylı)

### Senaryo 1 — LS checkout çalışmıyor (LS-side outage / API hata)

```text
Tetikleyici: LS API 5xx artışı, status.lemonsqueezy.com incident
Süre        : Genelde dakika–saat
Aksiyon     :
  - /app/billing/plans sayfasında banner: "Geçici olarak yeni abonelik
    alımına ara verdik. Mevcut hizmetiniz etkilenmedi."
  - Yeni abonelik POST /app/billing/checkout endpoint'i 503 döner
    (kullanıcıya "Lütfen daha sonra tekrar deneyin" mesajı)
  - LS webhook queue beklemeye devam eder (idempotent)
  - Mevcut active subscriptions etkilenmez (LS portal access bağımsız)
Owner       : Tek başına monitoring (PagerDuty / UptimeRobot)
Ack window  : 15 dakika (LS public status check)
```

### Senaryo 2 — LS payout gecikti (>7 gün)

```text
Tetikleyici: Banka transfer gecikmesi, LS finans review, payout schedule değişti
Süre        : 1-30 gün
Aksiyon     :
  - **30 gün operasyonel nakit tamponu** zorunlu (vergi danışmanı önerisi:
    şahıs ticari kazanç mükellefiyetinde aylık çalışma sermayesi)
  - support@lemonsqueezy.com ile yazılı iletişim (timeline alınır)
  - Şahıs banka hesabı USD bakiyesi tracking (mali müşavirle aylık)
  - Provider abstraction çalışmaya devam (LS hala satıcı, sadece
    payout banka'ya gecikiyor — kullanıcı operasyonu etkilenmez)
Owner       : Founder + mali müşavir
Ack window  : 7 gün (gecikme yazılı iletişim)
```

### Senaryo 3 — LS hesabı incelemeye alındı (under review)

```text
Tetikleyici: LS dashboard "Account under review" notification,
             checkout disable edilebilir
Süre        : Genellikle 5-30 gün
Aksiyon     :
  - LS support ile yazılı temas (talepler, doc, KYC)
  - **Paddle hesap ön başvurusu aktive et** (paddle.com — bu issue:
    [#471](https://github.com/selmanays/nodrat/issues/471))
  - Provider abstraction LS'den Paddle'a swap için hazır olmalı
  - Mevcut subscription'lara dokunulmaz; sadece yeni alım kapatılır
  - Migration plan: existing customers → notification email →
    self-service Paddle re-subscribe (manuel akış)
Owner       : Founder + avukat (LS communication review)
Ack window  : 24 saat (dashboard notification görüldüğünde)
```

### Senaryo 4 — LS hesabı kapandı (account closed)

```text
Tetikleyici: LS terminate kararı (review sonucu olumsuz)
Süre        : Genellikle 30-60 gün notice + transition window
Aksiyon     :
  - **72 saat içinde Paddle'a swap** — provider abstraction enabled
  - Existing subscription'lar: LS son cycle'a kadar çalışır,
    yenileme öncesi Paddle re-subscribe email
  - Yeni abonelik: Paddle hosted checkout (env-var flip)
  - Refund/dispute: LS tarafında pending olanlar LS dashboard'da
    son güne kadar çözülür; sonrasında banka chargeback
  - Webhook handler: LS event'leri kapanış tarihine kadar consume
  - Customer notification email (Resend) — durum + Paddle migration
    rehberi
Owner       : Founder + dev (provider swap deploy)
Ack window  : 72 saat (Paddle swap zorunlu)
```

### Senaryo 5 — Refund dispute oranı arttı

```text
Tetikleyici: Aylık refund dispute >5% (LS dashboard chargeback rate)
Süre        : Sürekli (önleyici tedbir)
Aksiyon     :
  - Refund policy'i sıkılaştır (örn. dijital istisnaları daha net,
    ToS ihlali kapsamını genişlet)
  - Abuse policy gözden geçir (account sharing, trial abuse,
    fingerprint detection)
  - Pricing page'de "ne dahil ne dahil değil" açık liste
  - Onboarding'de feature setting'leri net göster (sürpriz yok)
  - LS Smart Retry parametrelerini gözden geçir
Owner       : Founder + UX/copy
Ack window  : Aylık review (KS-3 conversion KPI yanında)
```

### Senaryo 6 — MRR > $3K threshold (Limited Şti. + TR alternatif)

```text
Tetikleyici: 3 ay rolling MRR ≥ $3K (bu doc'ta vergi danışmanı eşiği:
             $3K=review, $5K=plan, $10K=convert)
Süre        : Stratejik karar — 3-6 ay planlama
Aksiyon     :
  - Mali müşavirle Limited Şti. simülasyonu (vergi avantajı +
    operasyonel maliyet karşılaştırma)
  - $5K MRR'de Limited kuruluş hazırlığı başlat
  - $10K MRR'de Limited'e geçiş kuvvetle önerilir
  - **Bu noktada TR yerli ödeme alternatifleri** yeniden
    değerlendirilebilir — Limited Şti. olduğu için artık fizibıl
  - Hibrit yapı opsiyon: TR müşteri TR-yerli provider (Limited Şti.
    e-Arşiv), yurt dışı LS/Paddle MoR (kalır)
Owner       : Founder + mali müşavir + avukat
Ack window  : 3 ay (plan), 6 ay (transition başlangıç)
```

---

## 3. Provider Abstraction Kontrolü

`PaymentProvider` Protocol mimari prensibi (architecture.md A3) gereği LS ve Paddle eşit interface'e bağlı. Issue [#471](https://github.com/selmanays/nodrat/issues/471) implementation:

```python
class PaymentProvider(Protocol):
    def createCheckoutSession(self, plan_id: str, user_id: str) -> CheckoutResult
    def handleWebhook(self, headers: dict, body: bytes) -> WebhookEvent
    def cancelSubscription(self, subscription_id: str) -> None
    def getSubscriptionStatus(self, subscription_id: str) -> SubscriptionStatus
    def getCustomerPortalUrl(self, customer_id: str) -> str

# Adapters
class LemonSqueezyProvider(PaymentProvider): ...   # Primary (active)
class PaddleProvider(PaymentProvider): ...          # Fallback (scaffold)

# Runtime swap
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "lemon_squeezy")
provider = {
    "lemon_squeezy": LemonSqueezyProvider,
    "paddle": PaddleProvider,
}[PAYMENT_PROVIDER]()
```

**Swap drill (Senaryo 4 için):**
1. PADDLE_API_KEY + PADDLE_WEBHOOK_SECRET env-var update (sops/age)
2. PAYMENT_PROVIDER=paddle (env-var)
3. `docker compose up -d --force-recreate api web worker_*`
4. Smoke test: yeni abonelik → Paddle checkout açılır
5. Webhook test mode: Paddle dashboard'dan signal gönder

---

## 4. Paddle Hesap Ön Başvuru Durumu

| Adım | Durum | Tarih | Sorumlu |
|---|---|---|---|
| paddle.com hesap kayıt | ⏳ TODO | - | Founder |
| Business doc seti hazır | ⏳ TODO | - | Founder + avukat |
| ToS, Privacy, KVKK aydınlatma URL'leri Paddle'a verildi | ⏳ TODO | - | Founder |
| Refund policy URL'i Paddle'a verildi | ⏳ TODO | - | Founder |
| Tax setup (TR locale) | ⏳ TODO | - | Founder + vergi danışmanı |
| Test mode product/variant tanımı | ⏳ TODO | - | Founder |
| Webhook signing secret kayıt | ⏳ TODO | - | Founder + dev |
| PaddleProvider adapter scaffold | ⏳ TODO | - | Dev (#471) |
| Sandbox test webhook flow | ⏳ TODO | - | Dev |
| Production hesap onay | ⏳ TODO | - | Founder (Paddle review) |
| Provider swap drill | ⏳ TODO | - | Dev (deploy test) |

> **Pratik kural:** Paddle hesabı **launch öncesi test mode'da hazır olmalı**, production'a alınması gerekmez. Senaryo 3-4 tetiklendiğinde hızlıca production'a alınır.

---

## 5. 30 Gün Nakit Tampon Kuralı

Vergi danışmanı önerisi + R-FIN-04 mitigation:

```text
Hedef     : Aylık operasyonel maliyet × 1 ay (=30 gün) şahıs banka
            hesabında USD veya TL olarak tampon
Maliyet   : VPS Contabo (€20/ay), domain, email (Resend $10/ay),
            mali müşavir (~₺2K-3K/ay), ileride avukat retainer
Tahmini   : ~$300-500/ay → tampon $300-500
            (Limited Şti. sonrası: $1.000-2.000/ay → tampon)
Aksiyon   : LS payout aylık gelirinin %10-20'si "tampon" olarak
            ayrı hesap/cüzdan
Tracking  : Mali müşavir aylık raporu içinde "operasyonel nakit
            tamponu" kalemi
```

---

## 6. Acil İletişim (Senaryo 3-4 tetiklenirse)

```text
LS support       : support@lemonsqueezy.com
LS dashboard     : https://app.lemonsqueezy.com (urgent communications)
Paddle support   : help@paddle.com (hesap aktive olduktan sonra)
Mali müşavir     : [____________________]
Avukat           : [____________________]
Founder          : selmanaycom@gmail.com
```

---

## 7. İlişkili Dokümanlar / Issues

- [Risk Register v0.3 R-FIN-04](../strategy/risk-register.md) — risk tanımı + skor
- [Lemon Squeezy locked decision](../../wiki/decisions/lemon-squeezy-payment-provider.md) — alternatif tablosu (Paddle, Stripe Atlas)
- [Architecture A3](../engineering/architecture.md) — provider abstraction prensibi
- [Issue #471](https://github.com/selmanays/nodrat/issues/471) — Paddle adapter implementation
- [Issue #46 (closed)](https://github.com/selmanays/nodrat/issues/46) — Limited Şti. defer kararı (R-FIN-04 senaryo 6 sonrası reaktive)
- [Compliance Brief v0.2 §10](compliance-brief.md) — vergi/yapı durumu

---

**Son güncelleme:** 2026-05-08
**Sıradaki review:** Paddle hesap ön başvurusu tamamlandığında (#471 progress)
**Yayın:** internal — kullanıcıya açık değil (operasyonel doküman)
