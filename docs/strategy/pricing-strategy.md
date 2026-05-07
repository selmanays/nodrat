# Nodrat — Pricing Stratejisi

**Doküman türü:** Pricing & Packaging Strategy
**Sürüm:** v0.1
**Bağımlılık:** PRD v0.1, IA v0.1, Discovery v0.1, Competitive v0.1, Unit Economics v0.1
**Hedef:** Trial → Free → Paid akışındaki tier yapısı, fiyat noktaları, paket içerikleri ve dönüşüm mekanikleri.

---

## 0. Yönetici Özeti

```text
Tier yapısı (4 tier + opsiyonel paid trial):
  Free     : 0 TL — kayıtlı, 10 üretim/ay (kalıcı, downgrade default)
  Starter  : 249 TL/ay (~$8) — 100 üretim/ay [3 gün ücretsiz deneme]
  Pro      : 749 TL/ay (~$24) — 500 üretim/ay + Faz 5 stil profili [3 gün ücretsiz deneme]
  Agency   : 2.499 TL/ay (~$80) — 2.500 üretim/ay × 3 koltuk + premium [7 gün ücretsiz deneme]

TOFU (anonim/kayıtsız):
  Search-as-a-Service (#261) — public haber arama + cluster timeline
  Trial üretim YOK (cost optimizasyonu, bot abuse koruması)

Yıllık iskonto: 2 ay bedava (~%16.7)
Pricing display: TL primary, USD reference small text
Anchor: ChatGPT $20 → Starter $8 alt fiyat / Pro $24 eşdeğer + niş
```

---

## 1. Pricing Felsefesi

### 1.1 Çekirdek prensipler

```text
F1. Value-based, not cost-plus
    Kullanıcının kazandığı zaman/güven değerine göre fiyatla,
    sadece LLM maliyetine markup yapma.

F2. ChatGPT anchor altında bilinçli
    ChatGPT Plus ($20) hedef kitlede zaten var.
    Nodrat "ChatGPT yerine değil, yanına" pozisyonunda.
    Starter $8 ile "ChatGPT'ye + bunu da al" mesajı.

F3. Free tier loss leader, ama acıtan
    %5 conversion oranı için free user "değer almalı"
    AMA "yetmiyor" hissi de yaratılmalı.
    10 üretim/ay = günde <1 → orta kullanıcıyı zorlar.

F4. Pro tier kâr motoru
    Margin $20+ tek kullanıcı.
    GTM odağı Pro, Starter "merdiven".

F5. Türkçe pricing (TL primary)
    Türkiye fiyat algısı önemli.
    USD anchor sadece referans.

F6. Yıllık ödeme retention boost'u
    %16.7 iskonto = 2 ay bedava
    Cash flow + churn azalması (yıllık abone churn'lemez).

F7. Quota değil feature-based fark
    Tier'lar arası fark sadece sayı değil:
    Modes (current vs comparison), modeller (DeepSeek vs Haiku),
    görsel destekli (Faz 4), stil profili (Faz 5)
```

### 1.2 Pricing prensipleri (yapılmayacaklar)

```text
- Aşırı tier fragmentation (4 tier yeterli, 7 tier confusing)
- Per-seat pricing Free/Starter/Pro'da (sadece Agency)
- Hidden fees / overage charges (overage olmaz, throttle)
- Auto-upgrade (kullanıcı izni olmadan tier yükseltme yok)
- Annual lock-in cezası (refund pro-rata)
- "Contact us" enterprise (self-serve net)
- Lifetime deal (revenue boost ama LTV katleder)
```

---

## 2. Tier Yapısı

### 2.1 Paid Plan Trial (3-7 gün ücretsiz deneme)

> **2026-05-07 revize**: Eski "anonim/kayıtsız trial" konsepti kaldırıldı. Yerine paid plan'lara
> 3-7 gün ücretsiz deneme eklendi. Sebep: anonim trial bot abuse riski + maliyet, qualified
> conversion oranı düşük. TOFU funnel artık Search-as-a-Service (#261) üzerinden anonim ziyaretçileri
> haber arama deneyimine yönlendiriyor; kayıt → paid plan trial qualified funnel.

```text
Hedef:    Paid plan'a "düşük risk" giriş — ödeme bilgisi alarak ama 3-7 gün ücretsiz dene
Erişim:   Sadece kayıtlı kullanıcı (register sonrası plan seç)
Süre:
  - Starter trial : 3 gün (ücretsiz)
  - Pro trial     : 3 gün (ücretsiz)
  - Agency trial  : 7 gün (B2B karar süreci için daha uzun)

Ödeme:
  - Card-required (Iyzico tokenization, $0/0TL pre-auth)
  - Trial sonunda otomatik charge (D-1 email reminder)
  - Trial içinde cancel → no charge, Free tier'a düşer

Trial içinde erişim: Plan ne ise tam feature set
  - Starter trial → Starter feature matrix (100 gen/ay quota → 3-gün prorated ~10 gen)
  - Pro trial    → Pro feature matrix (500 gen/ay quota → 3-gün prorated ~50 gen)
  - Agency trial → Agency feature matrix (2.500 gen/ay → 7-gün prorated ~580 gen × 3 seat)

State machine:
  pending_trial → active_trial (3-7g) → grace (24h) → active_paid VEYA cancelled

Conversion mekaniği:
  - D-2 email: "Trial'inizin son 1 günü var, [dashboard link]"
  - D-1 in-app banner + email: "Yarın otomatik abonelik başlayacak"
  - D+1 (charge sonrası): "Hoşgeldiniz" email + ilk ay fatura
  - Cancel sonrası: NPS survey ("neden vazgeçtiniz?")

Anti-abuse:
  - Card fingerprint rate limit (aynı kart × farklı email = 1 trial max)
  - Email domain dedup (gmail+1, +2 vs aynı user)
  - Iyzico fraud check zaten built-in
```

### 2.1b Anonim ziyaretçi (kayıtsız)

```text
Üretim erişimi:  YOK
Search erişimi:  ✅ /ara public haber arama (#261 Search-as-a-Service)
Timeline:        ✅ /olay/[slug] cluster timeline
CTA:             "Bu konuda X paylaşımı üreteyim mi?" → register wall (Free)

Sebep: Anonim üretim cost ($2-10/ay 1K-5K user) + bot abuse riski +
düşük qualified conversion. Search hub TOFU yeterli — yayıncı pazarlığı
ile sinerji + SEO + viral.
```

### 2.2 Free (kayıtlı)

```text
Hedef:    Active user oluşturma, conversion funnel'a sokma
Sınır:    10 üretim/ay
Ücret:    0 TL
Erişim:
  ✅ Current + Weekly mode
  ❌ Archive / Comparison
  ✅ X paylaşımı + summary
  ❌ X thread / analysis / headline / calendar
  ✅ Kaynak gösterimi (full)
  ✅ Geçmiş kayıtlar (son 30 gün)
  ❌ Stil profili (Faz 5)
  ❌ Görsel destekli içerik (Faz 4)
  ✅ DeepSeek V3 (default)
  ❌ Haiku 4.5

Conversion mekaniği:
  - 7. üretimden sonra "Sınıra yaklaşıyorsun" banner
  - 10. üretim sonrası "Yenileme tarihine 12 gün" + Starter CTA
  - "Comparison mode istemez misin?" feature gating banner
```

### 2.3 Starter — 249 TL/ay (~$8)

```text
Hedef:    İlk paid tier, "value entry"
Sınır:    100 üretim/ay
Anchor:   ChatGPT'nin %40'ı
Erişim:
  ✅ Current + Weekly + Archive (Comparison hariç)
  ✅ X paylaşımı + thread + summary + headline
  ❌ Analysis (deep) / Content calendar
  ✅ Kaynak gösterimi (full + export)
  ✅ Geçmiş kayıtlar (sınırsız)
  ❌ Stil profili (Faz 5)
  ❌ Görsel destekli (Faz 4)
  ✅ DeepSeek V3 + OpenRouter Llama
  ❌ Haiku 4.5
  ✅ Email destek (48h response)

Yıllık: 2.490 TL (10 ay fiyatı)
USD ref: $8/ay, $80/yıl

Conversion mekaniği (Pro'ya yükseltme):
  - 70+ üretim/ay kullanıyorsa "Pro'ya geç" suggest
  - Comparison mode tıklayınca paywall
  - Stil profili Faz 5'te paywall
```

### 2.4 Pro — 749 TL/ay (~$24)

⚠️ **Research insight (2026-05-01):** Pro tier "her gün kullanan ciddi creator" pozisyonunda. Sabah brifi recurring use case sticky retention sağlar (Discovery Research §4.1). %19 araştırma katılımcısı "her gün kullanırım, alırım".

```text
Hedef:    Kâr motoru, P1A (creator) primer
Mesaj:    "Her gün kullanan ciddi creator için"
Sınır:    500 üretim/ay
Anchor:   ChatGPT Plus ile eşdeğer + niş güç
Erişim:
  ✅ TÜM modlar (Current, Weekly, Archive, Comparison)
  ✅ TÜM çıktı türleri (X post, thread, summary, analysis,
                         headline, calendar, briefing)
  ✅ Kaynak gösterimi + advanced filtering
  ✅ Geçmiş kayıtlar + export (JSON, CSV)
  ✅ Stil profili (Faz 5) — 3 profile slot
  ✅ Görsel destekli içerik (Faz 4) — verified entities
  ✅ DeepSeek + Haiku 4.5 (premium model)
  ✅ Priority queue (concurrent: 3)
  ✅ Email destek (24h)

Yıllık: 7.490 TL (10 ay fiyatı)
USD ref: $24/ay, $240/yıl

Conversion mekaniği (Agency'e):
  - Multi-seat ihtiyacı tetikleyici (paylaşım daveti)
  - Müşteri yönetimi feature gating (Faz 7+)
```

### 2.5 Agency — 2.499 TL/ay (~$80) — 3 koltuk

⚠️ **Research insight (2026-05-01):** P1B görüşmelerinde **multi-seat MUST**, optional değil. Ajanslar "ekip içi kullanım + onay akışı + per-brand stil profili" olmadan upgrade etmiyor. Yapısal şart.

```text
Hedef:    P1B (ajans), upside revenue
Sınır:    2.500 üretim/ay (toplam, koltuklara dağılımlı)
Koltuk:   3 (ek koltuk: 599 TL/ay) — MUST, optional değil
Erişim:
  ✅ Pro'nun tüm özellikleri
  ✅ 3 kullanıcı koltuğu (multi-seat)
  ✅ Stil profili — 10 profile slot (marka başına)
  ✅ Görsel destekli + premium VLM (Faz 4)
  ✅ Comparison mode'da Claude Sonnet 4.6 (en kaliteli)
  ✅ Bulk export (Excel, structured)
  ✅ Priority concurrent: 5 per seat
  ✅ Slack/dedicated email destek (12h)
  ✅ Erken feature erişimi
  ❌ White-label (Faz 7+)
  ❌ API access (Faz 7+)

Yıllık: 24.990 TL (10 ay fiyatı)
USD ref: $80/ay, $800/yıl

Notlar:
  - Yıllık vs aylık prefer ratio %60 hedefi
  - Müşteri faturalama için VAT/KDV doğru fatura zorunlu
  - Sales-assist opsiyonel: 3+ koltuk ihtiyacı varsa demo
```

---

## 3. Tier Karşılaştırma Matrisi

> **Trial state**: Starter/Pro/Agency satınalmasında 3-7 gün ücretsiz dene; trial içinde tam plan
> feature set'ine erişim (kota prorated). Trial içinde cancel → Free'ye downgrade. (§2.1)

| Özellik | Anonim | Free | Starter | Pro | Agency |
|---|---|---|---|---|---|
| **Aylık fiyat (TL)** | — | 0 | 249 | 749 | 2.499 |
| **Yıllık fiyat (TL)** | — | — | 2.490 | 7.490 | 24.990 |
| **Trial (ücretsiz)** | — | — | 3 gün | 3 gün | 7 gün |
| **Üretim/ay** | 0 | 10 | 100 | 500 | 2.500 |
| **Search (haber arama)** | ✅ public (#261) | ✅ | ✅ | ✅ | ✅ |
| **Koltuk** | — | 1 | 1 | 1 | 3 (ek 599 TL) |
| **Current mode** | search-only | ✅ | ✅ | ✅ | ✅ |
| **Weekly mode** | — | ✅ | ✅ | ✅ | ✅ |
| **Archive mode** | son 30 gün | ❌ | ✅ | ✅ | ✅ |
| **Comparison mode** | — | ❌ | ❌ | ✅ | ✅ |
| **X post** | — | ✅ | ✅ | ✅ | ✅ |
| **X thread** | — | ❌ | ✅ | ✅ | ✅ |
| **Summary** | — | ✅ | ✅ | ✅ | ✅ |
| **Analysis** | — | ❌ | ❌ | ✅ | ✅ |
| **Headline** | — | ❌ | ✅ | ✅ | ✅ |
| **Content calendar** | — | ❌ | ❌ | ✅ | ✅ |
| **Briefing** | — | ❌ | ❌ | ✅ | ✅ |
| **Kaynak gösterimi** | full + outbound link | full | full+export | full+filter | full+bulk |
| **Geçmiş süresi** | — | 30 gün | sınırsız | sınırsız | sınırsız |
| **Stil profili (F5)** | — | ❌ | ❌ | ✅ 3 slot | ✅ 10 slot |
| **Görsel destek (F4)** | — | ❌ | ❌ | ✅ | ✅ premium |
| **Default LLM** | — | DeepSeek | DeepSeek | Haiku 4.5 | Haiku 4.5 |
| **Premium LLM (Sonnet)** | — | ❌ | ❌ | ❌ | ✅ comparison |
| **Concurrent gen** | — | 1 | 2 | 3 | 5 / seat |
| **Saatlik rate** | 10 search/dk | 5/saat | 20/saat | 60/saat | 120/saat |
| **Destek** | — | community | email 48h | email 24h | priority 12h |
| **API erişimi (F7+)** | — | ❌ | ❌ | ❌ | gelecekte |

---

## 4. Trial Mekanikleri ve Conversion Funnel

> **2026-05-07 revize**: Anonim trial üretimi kaldırıldı. Yeni funnel: Anonim ziyaretçi
> public Search-as-a-Service kullanır → register wall ile Free tier → opsiyonel paid plan trial.

### 4.1 Funnel diyagramı

```text
[Landing page / SEO sayfası]
     │ %20-30 → public search (#261 Search-as-a-Service)
     ▼
[/ara — anonim haber arama, 10 search/dk]
     │ %15 → "X paylaşımı üreteyim mi?" CTA
     ▼
[Register wall — Free tier]
     │ %50 → register
     ▼
[Free: 10 üretim/ay observation]
     │ %15 → Starter trial başlat (3 gün ücretsiz, card-required)
     │ %3  → Pro trial başlat (3 gün ücretsiz)
     │ %0.5 → Agency trial başlat (7 gün ücretsiz, B2B)
     ▼
[Paid trial: 3-7 gün full feature]
     │ %60-70 → trial sonu charge (paid active)
     │ %30-40 → cancel (Free'ye downgrade)
     ▼
[Paid: monthly/annual]
     │
     ├─→ Starter %30 → Pro upgrade (6 ay içinde)
     ├─→ Pro %10 → Agency (creator → ajans pivot)
     └─→ Annual switch %25 (monthly subs)
```

### 4.2 Free → Paid Trial triggers

```text
T1. 7. üretim sonrası banner: "Sınıra yaklaşıyorsun, Starter'ı 3 gün ücretsiz dene"
T2. 10. üretim (limit) sonrası kart: "Yenileme 18 gün sonra. Starter trial?"
T3. Comparison mode arama → "Bu özellik Pro'da. 3 gün ücretsiz dene"
T4. Premium feature erişim denemesi → contextual upsell
T5. Email kampanyası: 14. gün "Aktif kullanıyorsun, Starter ile 10x kota?"
```

### 4.3 Paid Trial → Active Paid triggers (otomatik churn engelleme)

```text
T1. D-2 email: "Trial son 1 gün — özet kullanım: X üretim, Y feature kullandın"
T2. D-1 in-app banner: "Yarın 249 TL otomatik kesilecek; cancel anytime"
T3. D+0 (charge günü): basari → "Hoşgeldiniz email" + ilk fatura PDF
T4. D+0 (charge fail): retry 3 gün × Iyzico → fail → grace 7 gün → Free downgrade
T5. Trial cancel: NPS micro-survey "Neden? (1-5 yıldız + textarea)"
```

### 4.3 Free → Starter triggers

```text
S1. 7. üretim sonrası soft banner: "Sınıra yaklaşıyorsun"
S2. 10. üretim sonrası: "Comparison mode istemez misin?"
    + 7 günlük free Starter trial teklifi
S3. Comparison mode tıklayınca paywall
S4. "İçeriğini export et" → Starter feature
S5. Email kampanyası: gün 14 + gün 28 nudge
S6. "Geçmiş kayıtların 30 günden eski siliniyor" uyarı
```

### 4.4 Starter → Pro triggers

```text
P1. 70+ üretim ay sonu yaklaşıyor → "Pro'ya geçince 5x"
P2. Stil profili tıklayınca paywall (Faz 5)
P3. Görsel destekli tıklayınca paywall (Faz 4)
P4. Analysis output type tıklayınca paywall
P5. Yüksek kullanım kullanıcılarına özel email teklifi
```

---

## 5. Yıllık vs Aylık

### 5.1 Yıllık iskonto yapısı

```text
Aylık fiyat × 12 = "list"
Yıllık fiyat = list × 10/12 (2 ay bedava, %16.7 iskonto)

  Tier      Aylık × 12      Yıllık       Tasarruf
  ─────────────────────────────────────────────────
  Starter   2.988 TL        2.490 TL     498 TL
  Pro       8.988 TL        7.490 TL     1.498 TL
  Agency    29.988 TL       24.990 TL    4.998 TL
```

### 5.2 Yıllık düşünmenin avantajı

```text
Kullanıcıya:
  + 2 ay bedava (kalıcı tasarruf)
  + Fiyat artışından korunma
  + "Karar verdim, geri dönmem" psikoloji

Bize:
  + Cash flow upfront (büyüme yatırımı)
  + Churn rate %50 düşer (yıllık abone aylık churn'lemez)
  + LTV %30+ artar (annual cohorts)
  + Müşteri commitment sinyali
```

### 5.3 Yıllık → aylık downgrade politikası

```text
- Yıllık satın alma sonrası 14 gün iade hakkı
- 14 gün sonra refund yok (TR e-ticaret hukuk uyumlu)
- Kalan ay credit olarak hesaba ekleyemezsin
- "Pause" feature yok (Faz 7+ değerlendirilebilir)
```

---

## 6. Geographic Pricing

### 6.1 Birinci pazar — Türkiye (TL)

```text
Display: 249 TL/ay
USD ref: ($8) yanında küçük gri yazı
KDV/VAT: Fiyat dahil (B2C için kanun)
Faturalama: e-Arşiv fatura (Türkiye)
Ödeme: Iyzico veya PayTR (TL kart)
```

### 6.2 İkinci pazar — Uluslararası (USD)

```text
Display: $8/mo
TL ref: 249 TL küçük yazı
Faturalama: Stripe invoice
Ödeme: Stripe (USD/EUR card)
Aktivasyon: ≥1.000 paid TR kullanıcı sonra
```

### 6.3 Pazar başına ayar tablosu (gelecek)

```text
TR :  Listeli — $8 / 249 TL
EU :  Listeli — €8 / $8 (eşit)
US :  Listeli — $8 (anchor değişmez)
MENA: Future  — $5–6 (PPP ayarı)
LATAM: Future — $5–6 (PPP ayarı)

Karar: MVP'de sadece TR. EU/US Yıl 2.
```

---

## 7. Pricing Display Stratejisi

### 7.1 Pricing page layout

```text
[Headline] Hangi paket sana uygun?
[Toggle] Aylık | Yıllık (2 ay bedava)
[4 sütun] Free | Starter | Pro | Agency

Vurgular:
  Pro sütunu: "En popüler" badge
  Agency: "Ajanslar için"
  Free: "Hemen başla, ücretsiz"

Her tier altında:
  - Fiyat (büyük)
  - Aylık üretim sayısı
  - 4-6 ana feature bullet
  - "Seç" CTA

Detaylı karşılaştırma tablosu sayfanın altında.
```

### 7.2 In-app pricing display

```text
/app/usage:
  - Bu ayki kullanım progress bar
  - "Üretimleriniz X/100" tier gösterimi
  - "Yenileme tarihi: 28 gün"
  - "Pro'ya geçerek 5x üretim" CTA (kullanım %70+)

/app/billing/plans:
  - Aktif plan vurgusu
  - Diğer plan'ları compare edilebilir
  - Yıllık/aylık toggle aynı sayfada
  - Downgrade için "İletişim" linki (intentional friction)
```

### 7.3 Psikolojik fiyatlama

```text
- 249 / 749 / 2499 (9-ending klasik)
- TL display öncesinde sembol yok ("249 TL", "₺249" değil)
- Cents/kuruş yok (round number)
- Yıllık iskonto "%16.7" değil "2 ay bedava" mesajı
- "İptal et istediğinde" trust copy (her tier altında)
```

---

## 8. Kullanım Aşımı (Overage) Politikası

### 8.1 Soft limit yaklaşımı

```text
Yaklaşım: Hard cap (overage charge YOK)
Aşıldığında:
  - "Bu ay quota'n bitti" toast
  - Yenileme tarihi gösterilir
  - Bir tier yukarı CTA
  - Eski geçmiş okuma serbest (sadece üretim block)

Neden hard cap?
  - Beklenmedik fatura sürpriziyle güven kırma
  - Kullanıcı tahminini bozmama
  - Maliyet kontrolü (LLM cost runaway koruma)
```

### 8.2 Quota carryover

```text
Aylık kullanılmayan quota TAŞINMAZ (klasik SaaS standardı).
Yıllık kullanıcılarda bile aylık reset.
```

---

## 9. Kötüye Kullanım Koruması

### 9.1 Trial abuse

```text
- Browser fingerprint (Faz 6 yapısında bahsedildi)
- IP + cookie kombinasyonu
- Email throwaway domain blacklist (mailinator vs)
- Phone verification (yüksek abuse riskinde aktif)
- Trial start → email verify before usage
```

### 9.2 Free tier abuse

```text
- 1 hesap = 1 telefon numarası (Faz 6)
- Aynı domain'den >5 hesap → manual review
- VPN exit node detection (rate limit + flag)
- Bulk register pattern detection
```

### 9.3 Paid tier abuse

```text
- Account sharing detection (concurrent IP/device)
- API scraping pattern (anti-bot)
- Rate limit per user/saat
- Suspicious usage pattern → admin review queue
```

---

## 10. Refund ve Cancellation

### 10.1 Refund politikası

```text
Aylık abonelik:
  - Aboneliği iptal: anında, geri kalan ayı kullanır
  - Refund: yok (kullanılmış ay)

Yıllık abonelik:
  - 14 gün iade hakkı (TR e-ticaret hukuku)
  - Sonra refund yok, ay sonu iptal

Beta/early adopter:
  - 30 gün full refund (güven inşası)
```

### 10.2 Cancellation flow

```text
1. /app/billing/subscription → "İptal et"
2. Modal: "Neden ayrılıyorsun?"
   - Çok pahalı
   - Yeterince kullanmıyorum
   - Eksik özellik
   - ChatGPT yetiyor
   - Diğer (text)
3. "Pause 1 ay" alternative (Faz 7+ — şimdilik sadece downgrade)
4. Confirm → next renewal'da bitecek (anında iptal değil)
5. Reason analytics → product feedback loop
```

---

## 11. Pricing Test ve Iterasyon

### 11.1 A/B test planı (post-launch)

```text
T1. Anchor test: Starter $8 vs $12
    Hipotez: $8 daha çok signup, $12 daha yüksek revenue
    Metric: paid signup rate × ARPU

T2. Yıllık iskonto: 2 ay bedava vs 3 ay
    Hipotez: 3 ay daha çok yıllık conversion
    Metric: annual % of new paid

T3. Pro feature gating yeri
    Hipotez: Comparison mode'da paywall vs stil profilinde
    Metric: free → Pro conversion

T4. Pricing page layout
    Hipotez: 3 tier (Free/Pro/Agency) vs 4 tier
    Metric: pricing→checkout conversion
```

### 11.2 Pricing review cadence

```text
Aylık: ARPU, MRR, churn, conversion funnel
Çeyreklik: tier balance, upgrade paths, refund reasons
Yıllık: full pricing reset değerlendirmesi
       (early customer grandfather hakkı korunur)
```

---

## 12. Karar Noktaları

| ID | Karar | Önerim | Etki |
|---|---|---|---|
| D1 | TL primary mi USD? | TL primary, USD ref | TR pazar fit |
| D2 | Anchor: ChatGPT $20 | Starter $8 alt anchor | Alt fiyat agresif |
| D3 | Tier sayısı | 4 tier (+trial) | Kompleksite vs seçim |
| D4 | Yıllık iskonto oranı | 2 ay bedava (%16.7) | Standart sektör |
| D5 | Multi-seat hangi tier? | Sadece Agency | Pro karmaşık olmaz |
| D6 | Free tier üretim sayısı | 10/ay | %5 conversion break-even |
| D7 | Overage handling | Hard cap, no charge | Güven |
| D8 | Beta pricing | Lifetime "founding member" %50 | İlk 100 kullanıcı |
| D9 | Premium model erişimi (Haiku) | Pro+ | Margin koruma |
| D10 | Comparison Sonnet erişimi | Sadece Agency | Cost runaway |

---

## 13. Çapraz Referans

```text
Tier maliyetleri              → Unit Economics §3.2 doğrulama
%5 conv hedefi                → North Star: paid conversion KPI
Pro tier P1A primer           → Discovery: persona pricing match
Agency tier P1B primer        → Discovery: ajans multi-seat
Annual %25 hedef              → Success Metrics: cash flow KPI
Quota & rate limit            → IA §3.7 (PRD §3.7)
Iyzico/PayTR/Stripe           → Legal Risk: ödeme uyumluluk
Trial fingerprint             → Risk Register: abuse vector
Comparison mode paywall       → MVP Cut-list: Faz 2 scope
Stil profili paywall          → IA §13 Faz 5
```

---

**Sonuç:** Pricing yapısı **value-based**, Türkiye pazarına optimize, ChatGPT anchor altında bilinçli olarak konumlanmış. **Pro tier kâr motoru**, Starter merdiven, Free %5 conversion ile loss leader. Yıllık ödeme retention boost'u sağlar. Hard cap (overage yok) güven, soft upgrade triggers conversion rate'i sürdürür. İlk 6 ay sonra A/B test ile fiyat noktaları kalibre edilmeli.
