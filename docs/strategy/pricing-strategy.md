# Nodrat — Pricing Stratejisi

**Doküman türü:** Pricing & Packaging Strategy
**Sürüm:** v0.2 (2026-05-08 — USD primary + Lemon Squeezy MoR pivot, Iyzico/e-Arşiv reddedildi, Epic [#448](https://github.com/selmanays/nodrat/issues/448))
**Bağımlılık:** PRD v0.2, IA v0.1, Discovery v0.1, Competitive v0.1, Unit Economics v0.3
**Hedef:** Trial → Free → Paid akışındaki tier yapısı, fiyat noktaları, paket içerikleri ve dönüşüm mekanikleri.

> **v0.2 değişikliği:** Para birimi TL primary'den **USD primary**'e (TL display locale ile). Ödeme provider'ı Iyzico'dan **Lemon Squeezy (Merchant of Record)**'e. Bu LS satıcı sıfatıyla fatura keser → e-Arşiv altyapısı yok, Limited Şti. ilk lansmanda gereksiz. F5 prensibi (TL primary) ters çevrildi. §6 geographic + §10 refund LS hosted akışına göre yeniden yazıldı. Trade-off: komisyon %2.5 → %5+50¢ (margin %75 → %70 hedef).

---

## 0. Yönetici Özeti

```text
Tier yapısı (4 tier + opsiyonel paid trial):
  Free     : $0 — kayıtlı, 10 üretim/ay (kalıcı, downgrade default)
  Starter  : $8/ay — 100 üretim/ay [3 gün ücretsiz deneme]
  Pro      : $24/ay — 500 üretim/ay + Faz 5 stil profili [3 gün ücretsiz deneme]
  Agency   : $79/ay — 2.500 üretim/ay × 3 koltuk + premium [7 gün ücretsiz deneme]
              Multi-seat: variant_5_seats $129, variant_10_seats $249 (LS variant)

TOFU (anonim/kayıtsız):
  Search-as-a-Service (#261) — public haber arama + cluster timeline
  Trial üretim YOK (cost optimizasyonu, bot abuse koruması)

Yıllık iskonto: 2 ay bedava (~%16.7)
Pricing display: USD primary, TL display locale ile (referans, kullanıcının
                  bankası FX uygular)
Anchor: ChatGPT Plus $20 → Starter $8 alt fiyat / Pro $24 eşdeğer + niş
Payment provider: Lemon Squeezy (Merchant of Record) — LS müşteriye fatura
                  keser, payout Nodrat'a şahıs hesabına. Iyzico/e-Arşiv
                  reddedildi (Epic #448).
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

F5. USD primary, TL display locale (2026-05-08 revize)
    Lemon Squeezy MoR USD-native; TL native değil.
    Türkçe pricing copy korunur ama charge USD;
    kullanıcı bankası FX uygular (LS algıyı yumuşatır).
    Eski "TL primary" ilkesi #448 ile reddedildi
    (TR-only Iyzico planı yerine global LS).

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
  - Card-required (Lemon Squeezy native trial, $0 pre-auth)
  - Trial sonunda otomatik charge (D-1 email reminder)
  - Trial içinde cancel → no charge, Free tier'a düşer
  - LS hosted checkout (Nodrat custom payment form yok)

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
  - Lemon Squeezy fraud check zaten built-in (Stripe Radar altyapısı)
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

### 2.3 Starter — $8/ay (~249 TL display)

```text
Hedef:    İlk paid tier, "value entry"
Sınır:    100 üretim/ay
Anchor:   ChatGPT Plus'ın %40'ı ($20 → $8)
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

Yıllık: $80/yıl (10 ay fiyatı)
TL display ref: ~249 TL (anlık FX, LS USD charge)
LS variant: variant_starter_solo

Conversion mekaniği (Pro'ya yükseltme):
  - 70+ üretim/ay kullanıyorsa "Pro'ya geç" suggest
  - Comparison mode tıklayınca paywall
  - Stil profili Faz 5'te paywall
```

### 2.4 Pro — $24/ay (~749 TL display)

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

Yıllık: $240/yıl (10 ay fiyatı)
TL display ref: ~749 TL (anlık FX, LS USD charge)
LS variant: variant_pro_solo

Conversion mekaniği (Agency'e):
  - Multi-seat ihtiyacı tetikleyici (paylaşım daveti)
  - Müşteri yönetimi feature gating (Faz 7+)
```

### 2.5 Agency — $79/ay (~2.499 TL display) — 3 koltuk

⚠️ **Research insight (2026-05-01):** P1B görüşmelerinde **multi-seat MUST**, optional değil. Ajanslar "ekip içi kullanım + onay akışı + per-brand stil profili" olmadan upgrade etmiyor. Yapısal şart.

```text
Hedef:    P1B (ajans), upside revenue
Sınır:    2.500 üretim/ay (toplam, koltuklara dağılımlı)
Koltuk:   3 koltuk default — MUST, optional değil
LS variant yapısı (multi-seat = LS variant + custom seat counter, #451):
  - variant_3_seats : $79/ay   (default Agency)
  - variant_5_seats : $129/ay  (~$26/seat, 67% ek koltuk indirim)
  - variant_10_seats: $249/ay  (~$25/seat, daha agresif scale)
Erişim:
  ✅ Pro'nun tüm özellikleri
  ✅ 3-10 kullanıcı koltuğu (LS variant'a göre, multi-seat)
  ✅ Stil profili — 10 profile slot (marka başına)
  ✅ Görsel destekli + premium VLM (Faz 4)
  ✅ Comparison mode'da Claude Sonnet 4.6 (en kaliteli)
  ✅ Bulk export (Excel, structured)
  ✅ Priority concurrent: 5 per seat
  ✅ Slack/dedicated email destek (12h)
  ✅ Erken feature erişimi
  ❌ White-label (Faz 7+)
  ❌ API access (Faz 7+)

Yıllık: $790/yıl (3 seat) / $1.290/yıl (5 seat) / $2.490/yıl (10 seat) — 10 ay fiyatı
TL display ref: ~2.499 TL / 4.090 TL / 7.890 TL (anlık FX, LS USD charge)

Notlar:
  - Yıllık vs aylık prefer ratio %60 hedefi
  - Müşteri faturalama: LS MoR keser (Nodrat e-Arşiv kesmez — eski plan reddedildi #448)
  - Sales-assist opsiyonel: 10+ koltuk ihtiyacı varsa demo + custom variant
  - Seat ataması Nodrat side (agency_seats tablosu, davet email akışı)
```

---

## 3. Tier Karşılaştırma Matrisi

> **Trial state**: Starter/Pro/Agency satınalmasında 3-7 gün ücretsiz dene; trial içinde tam plan
> feature set'ine erişim (kota prorated). Trial içinde cancel → Free'ye downgrade. (§2.1)

| Özellik | Anonim | Free | Starter | Pro | Agency |
|---|---|---|---|---|---|
| **Aylık fiyat (USD)** | — | $0 | $8 | $24 | $79 (3 seat) / $129 (5 seat) / $249 (10 seat) |
| **TL display ref** | — | 0 | ~249 | ~749 | ~2.499 / ~4.090 / ~7.890 |
| **Yıllık fiyat (USD)** | — | — | $80 | $240 | $790 / $1.290 / $2.490 |
| **Trial (ücretsiz)** | — | — | 3 gün | 3 gün | 7 gün |
| **Üretim/ay** | 0 | 10 | 100 | 500 | 2.500 |
| **Search (haber arama)** | ✅ public (#261) | ✅ | ✅ | ✅ | ✅ |
| **Koltuk** | — | 1 | 1 | 1 | 3 / 5 / 10 (LS variant — #451) |
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
T4. D+0 (charge fail): LS Smart Retry (3-7 gün) → grace 7 gün → Free downgrade (LS dunning otomatik)
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

  Tier            Aylık × 12      Yıllık       Tasarruf
  ───────────────────────────────────────────────────────
  Starter         $96             $80          $16
  Pro             $288            $240         $48
  Agency 3-seat   $948            $790         $158
  Agency 5-seat   $1.548          $1.290       $258
  Agency 10-seat  $2.988          $2.490       $498

LS variant naming: variant_<plan>_yearly (örn. variant_pro_solo_yearly).
TL display ref: anlık FX × USD, kullanıcı bankası FX uygular.
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

## 6. Geographic Pricing — Lemon Squeezy MoR (global)

> **2026-05-08 revize (Epic #448):** TR-only Iyzico planı reddedildi. Lemon Squeezy MoR ile **global launch from day 1**. Tek currency (USD) tek payment infrastructure. LS müşteriye fatura keser, KDV/VAT/sales tax global yönetir, Nodrat'a payout net revenue olarak gönderir.

### 6.1 Birincil currency — USD

```text
Display: $8 / $24 / $79 (TL display locale ile yan yana ~249 TL)
KDV/VAT: LS müşteri lokasyonuna göre handle eder (TR %20 KDV LS keser, AB VAT LS keser)
Faturalama: LS hosted invoice — Nodrat e-Arşiv kesmez (eski plan #448 ile reddedildi)
Ödeme: Lemon Squeezy hosted checkout (USD/EUR/GBP card)
```

### 6.2 TR pazarı — USD charge + TL display

```text
Display: USD primary ($8/ay) + TL display locale (~249 TL anlık FX)
Charge: USD (LS USD-native)
FX: Kullanıcının bankası TL → USD dönüşüm uygular
TR-spesifik notlar:
  - Bazı TR bankalar yurt dışı kart işlemi için ek %1-3 komisyon alabilir
  - TL → USD volatility kullanıcı algısını etkileyebilir (TL devalüe edince ay başı yeniden hesap görünür)
  - Mitigation: pricing page'de "yaklaşık" USD anchor + sabit USD listing
KDV (TR): LS MoR sıfatıyla TR KDV %20'yi keser, müşteriye fatura kesmesinde dahil
```

### 6.3 Pazar başına ayar tablosu (gelecek)

```text
TR :  $8 / $24 / $79 (USD charge, TL display ~249 / ~749 / ~2.499)
EU :  $8 / $24 / $79 (LS VAT keser, KDV/VAT dahil display)
US :  $8 / $24 / $79 (anchor değişmez, sales tax LS keser)
UK :  £6 / £19 / £63 (~) (LS GBP variant alternatif — Yıl 2)
MENA: Future  — $5–6 (PPP ayarı, LS variant)
LATAM: Future — $5–6 (PPP ayarı, LS variant)

Karar: MVP-3'te global launch (LS sayesinde geo-restriction yok).
       PPP variant'ları Yıl 2.
```

### 6.4 Eski plan archive (ne reddedildi, neden)

```text
2026-05-01 Pricing v0.1 plan (Iyzico, TL primary):
  TR Iyzico (TL kart) + e-Arşiv fatura → Limited Şti. + muhasebe altyapısı
  EU/US Stripe USD → ≥1.000 paid TR kullanıcı sonra aktivasyon
Reddedilme nedeni: Limited Şti. kuruluşu (~6-8 hafta) + e-Arşiv altyapı maliyeti
                   solo founder + bootstrap context'te launch'u 2-3 ay erteler.
                   Lemon Squeezy MoR aynı işi tek provider ile yapar.
Karar: Epic #448 (2026-05-08), [[lemon-squeezy-payment-provider]] locked decision.
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
- $8 / $24 / $79 (round USD, 9-ending Pro $24 yerine $25 değil — anchor under ChatGPT $20)
- USD currency display: "$8/mo" (no decimals, M/Y suffix)
- TL display ref smaller: "(~249 TL)" italic, gri
- Yıllık iskonto "%16.7" değil "2 ay bedava" mesajı
- "İptal et istediğinde" trust copy (her tier altında)
- "Vergi LS tarafından kesilir" microcopy (KDV/VAT compliance assurance)
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

### 10.1 Refund politikası — LS hosted

```text
Aylık abonelik:
  - Aboneliği iptal: anında, geri kalan ayı kullanır
  - Refund: yok (kullanılmış ay) — LS hosted refund flow

Yıllık abonelik:
  - 14 gün iade hakkı (TR e-ticaret hukuku + AB cooling-off period)
  - LS otomatik prorate refund hesaplar
  - Sonra refund yok, ay sonu iptal

Beta/early adopter:
  - 30 gün full refund (güven inşası)
  - LS dashboard manuel refund (ya da customer support email)

Önemli — LS MoR sorumluluğu:
  - Refund/chargeback LS yönetir, Nodrat manuel müdahale yok
  - LS refund onayında payout azaltır (Nodrat hesabından düşülür)
  - Chargeback fee $15-20 (LS hesaba yansıtır)
```

### 10.2 Cancellation flow — LS Customer Portal

```text
1. /app/billing/manage → "Aboneliği yönet" → LS hosted Customer Portal redirect
2. LS portal:
   - Cancel subscription
   - Update payment method
   - Change plan (variant değişimi)
   - Invoice history + PDF download
3. Cancel sonrası Nodrat webhook subscription_cancelled alır → DB update
4. Confirm → next renewal'da bitecek (anında iptal değil), kullanıcı geri kalan
   period'u kullanır
5. Reason analytics: LS exit survey (opsiyonel) + Nodrat /app/billing/canceled
   sonrası soft survey ("Neden ayrıldın?")

Out of scope (Faz 7+):
  - "Pause 1 ay" alternative (LS native pause yok; manuel implement)
  - In-app cancel modal (LS portal hosted)
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

| ID | Karar | Karar (v0.2) | Etki |
|---|---|---|---|
| D1 | Para birimi | **USD primary, TL display locale** (v0.1 "TL primary" reddedildi #448) | Global launch hazır, TR FX algısı kabul |
| D2 | Anchor: ChatGPT $20 | Starter $8 alt anchor | Alt fiyat agresif |
| D3 | Tier sayısı | 4 tier (+trial) | Kompleksite vs seçim |
| D4 | Yıllık iskonto oranı | 2 ay bedava (%16.7) | Standart sektör |
| D5 | Multi-seat hangi tier? | Sadece Agency (LS variant 3/5/10 seat) | Pro karmaşık olmaz; LS variant + counter (#451) |
| D6 | Free tier üretim sayısı | 10/ay | %5 conversion break-even |
| D7 | Overage handling | Hard cap, no charge | Güven |
| D8 | Beta pricing | Lifetime "founding member" %50 | İlk 100 kullanıcı |
| D9 | Premium model erişimi (Haiku) | Pro+ | Margin koruma |
| D10 | Comparison Sonnet erişimi | Sadece Agency | Cost runaway |
| D11 | **Payment provider** | **Lemon Squeezy MoR** (Iyzico/PayTR/Stripe-direct reddedildi) | Limited Şti. gereksiz, e-Arşiv kalktı, %5+50¢ fee |
| D12 | **Margin hedef** | **≥%70** paid tier (eski %75 LS fee öncesi hedefiydi) | LS MoR ~%5+50¢ + tax handling fee dahil |

---

## 13. Çapraz Referans

```text
Tier maliyetleri              → Unit Economics §3.2 doğrulama
%5 conv hedefi                → North Star: paid conversion KPI
Pro tier P1A primer           → Discovery: persona pricing match
Agency tier P1B primer        → Discovery: ajans multi-seat
Annual %25 hedef              → Success Metrics: cash flow KPI
Quota & rate limit            → IA §3.7 (PRD §3.7)
Lemon Squeezy MoR             → [[lemon-squeezy-payment-provider]] (Epic #448), Legal Risk: KVKK m.9 cross-border
Trial fingerprint             → Risk Register: abuse vector
Comparison mode paywall       → MVP Cut-list: Faz 2 scope
Stil profili paywall          → IA §13 Faz 5
```

---

**Sonuç:** Pricing yapısı **value-based**, **USD primary global launch** (Lemon Squeezy MoR sayesinde geo-restriction yok), ChatGPT Plus anchor altında bilinçli olarak konumlanmış. **Pro tier kâr motoru** ($24, ~$22.30 net post-LS-fee), Starter merdiven, Free %5 conversion ile loss leader. Yıllık ödeme retention boost'u sağlar. Hard cap (overage yok) güven, soft upgrade triggers conversion rate'i sürdürür. LS MoR sayesinde Limited Şti. gereksiz, e-Arşiv altyapı kalktı, refund/chargeback hosted — solo founder operasyonel yük minimum. İlk 6 ay sonra A/B test ile fiyat noktaları kalibre edilmeli.
