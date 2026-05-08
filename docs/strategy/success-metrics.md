# Nodrat — Başarı Metrikleri ve North Star

**Doküman türü:** Success Metrics & KPI Framework
**Sürüm:** v0.2 (2026-05-08 — currency note: USD primary, Epic [#448](https://github.com/selmanays/nodrat/issues/448))
**Bağımlılık:** PRD v0.2, IA v0.1, Discovery v0.1, Competitive v0.1, Unit Economics v0.3, Pricing v0.2, Risk Register v0.3

> **v0.2 currency note (Epic #448):** Tüm KPI değerleri **USD primary** olarak ölçülür (MRR, ARPU, LTV, CAC). TL display ref opsiyonel. Lemon Squeezy MoR'a geçiş sonrası KPI'lar net revenue (post-LS-fee) bazında raporlanır — ek "gross MRR" sütunu opsiyonel. Pre-pivot TL bazlı target'lar (örn. "WTP ≥250 TL") USD karşılığına çevrildi: ≥$8 ≅ Starter price anchor.
**Hedef:** "Başardık" ne demek? Tek north star metric ve onun altında yatan KPI ağacı + alarm eşikleri.

---

## 0. Yönetici Özeti

```text
North Star Metric:
  Weekly Saved Generations per Active User (WSGAU)
  
  Tanım: Bir aktif kullanıcının haftada "Kaydet" butonuna bastığı
         üretim sayısı. Hem kullanım (gen sayısı) hem kalite
         (kaydedilmeye değer) sinyallerini birleştirir.

  Hedef:
    Pilot (MVP-1):     ≥ 1.5  (haftada en az 1-2 değerli üretim)
    Beta (MVP-2):      ≥ 2.5
    Public (MVP-3):    ≥ 3.5
    Olgun (Yıl 1):     ≥ 5.0

KPI ağacı (4 ana dal):
  1. Acquisition  → trial start, register, source CTR
  2. Activation   → ilk üretim, ilk save, aha moment
  3. Retention    → D1/D7/D30, churn
  4. Revenue      → conversion, ARPU, MRR

Faz bazlı odak:
  MVP-1: Activation (ürün çalışıyor mu?)
  MVP-2: Retention (kullanıcı dönüyor mu?)
  MVP-3: Revenue (ödüyor mu?)
  Olgun: Tüm dört dal optimize
```

---

## 1. Metrik Felsefesi

### 1.1 Çekirdek prensipler

```text
P1. Output > Input
    "Kaç haber kazıdık" değil "kaç kullanıcı içerik kaydetti"
    Vanity metric'leri minimum tut.

P2. Single North Star
    Tek metric organize eder. WSGAU çelişkili optimize edemez:
    - Sadece gen artırırsak save düşer (kalite koruması)
    - Sadece save artırırsak gen düşer (etkileşim koruması)

P3. Leading + lagging karışımı
    Lagging (MRR, retention) sonuç gösterir
    Leading (saved gen, NPS, activation) yön gösterir

P4. Faz-spesifik odak
    MVP-1'de revenue metrik konuşmak anlamsız (paid user yok)
    Her faz farklı bir KPI ağırlığı

P5. Ölçemediğin şeyi yönetemezsin
    Her KPI'nın bir kaynak (source-of-truth) tablosu olmalı
    Manual hesaplama dışına çıkmamalı

P6. Aleihteki metrikleri zorunlu izle
    "Nelere bakmamak istiyorum?" da önemli
    Halüsinasyon oranı, churn reason, support ticket
```

### 1.2 Anti-metrikler (yapılmayacak ölçümler)

```text
- "Toplam haber havuzu" (input vanity)
- "Toplam embedding" (compute vanity)
- "Toplam kullanıcı" (paid değilse anlamsız)
- "Toplam tweet üretildi" (kaydet/yayınla yoksa boş)
- "X follower" (Nodrat'ın kendi X hesabı için relevant değil)
- DAU/MAU (Türkiye SaaS için MAU yeterli, DAU zoraki)
```

---

## 2. North Star Metric — WSGAU

### 2.1 Tanım

```text
WSGAU = Weekly Saved Generations per Active User

Hesap:
  numerator   = O hafta "save" edilen toplam üretim sayısı
  denominator = O hafta aktif (≥1 üretim yapan) kullanıcı sayısı

Aktif kullanıcı tanımı:
  Son 7 gün içinde ≥1 generation yapmış kayıtlı user

Save tanımı:
  /app/saved'e eklenmiş üretim VEYA
  Kullanıcı clipboard'a kopyalamış (analytics event)
```

### 2.2 Neden bu metrik?

```text
- Kullanım sinyali var (gen yapmadan save olmaz)
- Kalite sinyali var (save sadece "değerli" için)
- Manipule edilmesi zor (gen sayısını şişirsen save oranı düşer)
- Tüm tier'larda anlamlı (free user'da da, Pro'da da)
- Faz bağımsız (MVP-1'de de ölçülebilir)
- Türkçe creator'ın "ne kadar değer aldım" cevabıyla uyumlu

Alternatif north star adayları (reddedildi):
  - "X paylaşımı yapılan üretim" → X hesap entegrasyonu yok
  - "MRR" → MVP-1'de paid user yok, çok geç sinyal
  - "DAU" → Türkiye'de günlük gelmek doğal değil; haftalık doğru
  - "Generation count" → kalite filtresi yok
```

### 2.3 Hedef trajektori

```text
Faz             Hedef    Notlar
──────────────────────────────────────────────────────
MVP-1 (alpha)   1.5     "Kullandı ve değer aldı" baseline
MVP-1 (closed)  2.0     Kullanıcı geri dönüyor
MVP-2 (beta)    2.5     Activation döngüsü oturmuş
MVP-2 (open)    3.0     Genel kullanım sağlıklı
MVP-3 launch    3.5     Paid user'lar daha çok save eder
Yıl 1 sonu      5.0     Olgun ürün, retention oturmuş
Yıl 2           6.0+    Paid mix değişir, niş derinleşir
```

### 2.4 Segment kırılımları

```text
Tüm WSGAU rakamı segment bazlı raporlanmalı:

  Segment        WSGAU hedef (Yıl 1)
  ─────────────────────────────────────
  Free           3.0   (loss-leader, daha aktif)
  Starter        5.0   (paying gives commitment)
  Pro            7.0   (heavy users, multiple use cases)
  Agency seat    8.0   (her seat birden fazla marka)

Segmenter arası WSGAU farkı tier sağlıklı çalıştığını gösterir.
```

---

## 3. KPI Ağacı

### 3.1 Üst seviye: AARRR + Operational

```text
                       WSGAU (North Star)
                              │
        ┌──────────┬──────────┼──────────┬──────────┐
        ▼          ▼          ▼          ▼          ▼
   ACQUISITION ACTIVATION RETENTION   REVENUE    QUALITY
                                                    │
                                              Operasyonel
                                              metrikler
```

### 3.2 ACQUISITION (kullanıcı edinme)

```text
A1.  Landing page CTR              %   (visitor → trial start)
A2.  Trial start count             #   /day, /week
A3.  Register count                #   /day, /week
A4.  Trial → Free conversion       %   (≥%25 hedef)
A5.  Source: hangi kanal           %   organic / paid / referral / social
A6.  CAC (cost per acquisition)    $   paid kanalda
A7.  Time-to-register              s   landing → register median
A8.  Email verify rate             %   (≥%80 hedef)
```

### 3.3 ACTIVATION (ilk değer)

⚠️ **Research confirmed (2026-05-01):** B5 "ilk SAVE = aha moment" prototype testinde doğrulandı. Save + clipboard copy kullanıcılar tarafından "değer aldım" sinyali olarak güçlü onaylandı. Discovery findings §4.2.

```text
B1.  First generation rate         %   register → first gen (≥%70 hedef)
B2.  Time-to-first-generation      s   median
B3.  First save rate                %   register → first save (≥%40)
B4.  Time-to-first-save             s   median
B5.  "Aha moment" tanımı           —    İlk SAVE veya CLIPBOARD COPY = aha moment ✅ confirmed
B6.  Activation funnel             %   her adım
B7.  Drop-off points               —    nerede kaybediyoruz
B8.  Onboarding completion          %   (Faz 6+ onboarding flow)
```

### 3.4 RETENTION (geri dönüş)

```text
C1.  D1 retention                  %   ertesi gün geri gelen
C2.  D7 retention                  %   1 hafta sonra geri
C3.  D30 retention                 %   1 ay sonra geri
C4.  Weekly active users (WAU)     #
C5.  Monthly active users (MAU)    #
C6.  WAU/MAU ratio                 %   (≥30 sağlıklı)
C7.  Churn rate (paid)             %   monthly (<%5 hedef)
C8.  Reactivation rate              %   churned → returning
C9.  Cohort retention (saved)      —    save eden cohort retention vs eden değil
```

### 3.5 REVENUE (Faz 6+ kritik)

```text
D1.  Paid conversion (free → paid)  %   ≥%5 (Pricing Strategy)
D2.  ARPU                          $   /user/month average
D3.  ARPPU                         $   /paying user/month
D4.  MRR                            $   monthly recurring
D5.  ARR                            $   annual run rate
D6.  LTV                            $   lifetime value (cohort)
D7.  LTV / CAC ratio                —    (≥3:1 sağlıklı)
D8.  Annual upgrade rate           %   monthly → annual
D9.  Tier upgrade rate             %   Starter → Pro etc
D10. Refund rate                   %   <%2 sağlıklı
```

### 3.6 QUALITY (AI özel)

```text
E1.  Halüsinasyon flag rate        %   kullanıcı flag / total gen
E2.  Insufficient data rate        %   "veri yetersiz" output / total
E3.  Source citation rate          %   her gen kaynak gösterdi mi
E4.  Generation success rate       %   error olmadan tamamlanan
E5.  Latency p50/p95/p99           s   gen submit → result
E6.  NPS                            #   beta + sürekli
E7.  Support ticket / 1K user      #   (<5 sağlıklı)
E8.  Feature usage %               —    her output type kullanım
E9.  Mode usage %                  —    current vs weekly vs comparison
```

### 3.7 OPERATIONAL (admin operasyon)

```text
F1.  Source success rate           %   /day per source
F2.  Source health green count     #   /total sources
F3.  Average extraction confidence  —    PRD §1.5 metric
F4.  Articles ingested              #   /day, /week
F5.  Duplicate detection rate      %   correctly flagged
F6.  Embedding queue lag           s   submit → indexed
F7.  Failed jobs / total           %   <%1 hedef
F8.  Provider error rate           %   per provider
F9.  Disk usage                    GB  Postgres + MinIO
F10. Backup success                %   günlük

F11. Cost per generation           $   real-time
F12. Daily provider spend          $   per provider
F13. Per-user cost (P95)           $   anomaly detection
```

---

## 4. Faz Bazlı KPI Önceliği

### 4.1 MVP-1 (8-12 hafta) — "Çalışıyor mu?"

```text
Birincil:
  - WSGAU baseline (≥1.5)
  - Generation success rate (≥%95)
  - Source success rate (≥%70)
  - First generation rate (activation)
  - Halüsinasyon flag rate (<%5)

İzlenen ama optimize edilmeyen:
  - Retention (henüz cohort yok)
  - Revenue (paid user yok)

İhmal edilen:
  - CAC, LTV, MRR
  - Paid conversion
  - Yıllık iskonto
```

### 4.2 MVP-2 (6-8 hafta sonra) — "Geri dönüyor mu?"

```text
Birincil:
  - WSGAU growth (1.5 → 2.5)
  - D7 retention (≥%30)
  - D30 retention (≥%15)
  - Beta NPS (≥30)
  - Activation funnel optimize (B1, B3)

Yeni eklenen:
  - Cohort analizi
  - Drop-off heatmap
  - Feature usage breakdown
```

### 4.3 MVP-3 (paid launch) — "Ödüyor mu?"

```text
Birincil:
  - Free → paid conversion (≥%5)
  - MRR growth rate
  - Churn rate (<%7 ilk ay, <%5 hedef)
  - LTV / CAC ratio (≥3 ideal, ≥1.5 minimum)
  - Trial → free conversion (≥%25)

Yeni eklenen:
  - ARPU, ARPPU
  - Tier upgrade rate
  - Refund rate
  - Annual subscription %
```

### 4.4 Olgun (Yıl 1+) — "Sürdürülebilir mi?"

```text
Birincil (sürekli izlenen):
  - WSGAU (≥5 hedef)
  - MRR growth (m/m %5+ hedef)
  - Net revenue retention (≥%100 ideal)
  - LTV / CAC (≥3:1)
  - Halüsinasyon rate (<%2)

Yeni eklenen:
  - Cohort LTV trajectory
  - Churn reason analysis
  - Expansion revenue (upgrade)
  - Brand awareness (organic search)
```

---

## 5. Dashboard Yapısı

### 5.1 Tek-bakışta dashboard (admin)

```text
┌─────────────────────────────────────────────────────────────┐
│  NODRAT — North Star Dashboard               [Bu hafta ▼]   │
├─────────────────────────────────────────────────────────────┤
│  WSGAU: 2.7        WAU: 145        MRR: $2,340               │
│   ↑ %12 vs L7      ↑ %5            ↑ %18                     │
├─────────────────────────────────────────────────────────────┤
│  Acquisition       Activation      Retention     Revenue     │
│  Trial→Free 28%    First Gen 72%   D7  34%       Conv 4.2%  │
│  Register/wk 89    First Save 41%  D30 18%       ARPU $12.3 │
├─────────────────────────────────────────────────────────────┤
│  Quality                          Operational                │
│  Halu flag  1.2%   Latency p95  3.2s    Source healthy 47/50│
│  Citation   100%   Success rate 98.1%   Cost/gen   $0.003   │
├─────────────────────────────────────────────────────────────┤
│  ⚠️ Alarmlar:                                                │
│   - Source "Habertürk" health red (3 saattir failure)        │
│   - Daily DeepSeek spend $42 → cap $50 yaklaşıyor             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Dashboard hierarchy

```text
Level 1: North Star (1 metric, hero number)
Level 2: AARRR özet (4 metric)
Level 3: Detay her dal için (5-10 metric)
Level 4: Drill-down (segment, cohort, source)
```

### 5.3 Reporting cadence

```text
Real-time:    cost spend, error rate, queue lag
Hourly:       active sessions, gen rate
Daily:        WAU, source health, cost per gen
Weekly:       WSGAU, retention cohort, support tickets
Monthly:      MRR, churn, NPS, full retro
Quarterly:    LTV, cohort projections, pricing review
Yıllık:       Strategy review, full pivot assessment
```

---

## 6. Alarm Eşikleri

### 6.1 Kırmızı alarm (anında müdahale)

```text
🚨 R1. Generation success rate < %85 (15 dk pencerede)
🚨 R2. Source success rate < %50 (1 saat)
🚨 R3. Daily provider spend > 1.5x avg
🚨 R4. Per-user cost > $5/gün
🚨 R5. Halüsinasyon flag > %5/gün
🚨 R6. Failed jobs queue > 1.000
🚨 R7. Embedding queue lag > 30 dk
🚨 R8. Disk usage > %85
🚨 R9. Backup başarısız (3 gün üst üste)
🚨 R10. Cyber security alert (auth failure spike)
```

### 6.2 Sarı uyarı (24h içinde değerlendir)

```text
⚠️  Y1. WSGAU 2 hafta üst üste düşüş
⚠️  Y2. D7 retention <%25 (yeni cohort)
⚠️  Y3. Paid conversion <%3 (aylık)
⚠️  Y4. Churn rate >%8 (aylık)
⚠️  Y5. NPS düşüş ≥10 puan
⚠️  Y6. Source "yellow" >5 (toplam aktif kaynaktan)
⚠️  Y7. Trial → free <%20
⚠️  Y8. Latency p95 > 5 saniye
⚠️  Y9. Refund rate > %3
⚠️  Y10. Support ticket / kullanıcı ≥10
```

### 6.3 Yeşil sinyal (kutlama, doğrulama)

```text
🟢 G1. WSGAU Q/Q ≥ %20 büyüme
🟢 G2. NPS ≥ 50 sürekli
🟢 G3. Net revenue retention ≥ %110
🟢 G4. LTV/CAC ≥ 5:1
🟢 G5. Annual subscription oranı ≥ %40
🟢 G6. Pro tier kullanıcı oranı ≥ %20
```

---

## 7. Cohort Analizi

### 7.1 Hangi cohort'lar takip edilecek?

```text
Acquisition cohort:
  - Aylık: register-month-cohort
  - Source: organic / paid / referral
  - Persona segment (eğer biliniyorsa)

Tier cohort:
  - Free / Starter / Pro / Agency
  - Annual / Monthly

Activation cohort:
  - First-save var mı yok mu (binary)
  - First-week active days (1, 2, 3+ )

Quality cohort:
  - Halüsinasyon flagleyen kullanıcılar
  - Insufficient data alan
```

### 7.2 Retention cohort tablosu

```text
              D1     D7     D14    D30    D60    D90
Cohort 2026-05  85%   42%   28%    18%    12%    8%
Cohort 2026-06  88%   45%   32%    21%    14%    10%
Cohort 2026-07  ...

Hedef: D7 ≥%30, D30 ≥%15 her cohort
       Trend: yeni cohort eski cohort'tan iyi
```

---

## 8. Survey ve Kalitatif Metrik

### 8.1 NPS

```text
"0-10 arası, Nodrat'ı arkadaşına ne kadar tavsiye edersin?"

Trigger:
  - 30 gün aktif olduktan sonra (1x)
  - Pro tier upgrade sonrası
  - Cancellation flow'unda

Hedef:
  Pilot:  ≥0 (henüz yeni)
  Beta:   ≥30 (genel SaaS avg)
  Olgun:  ≥50 (üst sınıf)
```

### 8.2 PMF Survey ("How would you feel?")

```text
"Eğer Nodrat artık olmasaydı nasıl hissederdin?"
  - Çok hayal kırıklığı (very disappointed)
  - Biraz hayal kırıklığı
  - Hayal kırıklığı yaşamam
  - Kullanmıyorum zaten

PMF eşiği: ≥%40 "very disappointed"
Trigger:    30 gün aktif sonrası

Bu Sean Ellis testi PMF onayı için altın standart.
```

### 8.3 Cancellation reason (zorunlu)

```text
İptal akışında:
  - Çok pahalı
  - Yeterince kullanmıyorum
  - Eksik özellik (text)
  - ChatGPT yetiyor
  - Kalite memnun etmedi
  - Diğer (text)

Aylık analiz, MVP roadmap girdisi.
```

---

## 9. Anti-Pattern'ler

```text
- "Vanity metric" sayımı (toplam haber, embedding)
- Tek bir metric'e tüm odaklanma → counter-metric ihmali
- Cherry-picking (sadece iyi gözüken cohort)
- Manual data extraction (otomatize edilmeli)
- Survey ile gerçek behavior'u doğrulamamak
- Faz-erken metric'ler (MVP-1'de MRR konuşma)
- Outlier'ları silmek (incelemek lazım)
- Avg yerine median (skewed data için)
```

---

## 10. Tooling

### 10.1 Self-hosted minimum

```text
Event tracking:
  - PostHog (self-host) → hem analitik hem feature flag
  - Plausible (self-host) → web analytics, GDPR friendly

Database analytics:
  - Postgres queries (raw)
  - Metabase (self-host) → dashboard

Error tracking:
  - Sentry (free tier veya self-host)

Cost tracking:
  - Custom tablo: provider_costs (per-call ledger)
  - Daily aggregate dashboard

Survey:
  - Typeform veya Tally (free tier)
  - In-app survey (PostHog feature)
```

### 10.2 Faz dahilinde araç eklemeleri

```text
Faz 0:  PostgreSQL queries + Excel
Faz 1:  PostHog event tracking aktif
Faz 2:  Metabase dashboard self-host
Faz 3:  Survey altyapısı (NPS, PMF)
Faz 6:  Stripe / Iyzico revenue tracking
Yıl 1:  Cost intelligence dashboard (custom)
```

---

## 11. Karar Noktaları

| ID | Karar | Önerim | Etki |
|---|---|---|---|
| D1 | North Star metric | WSGAU | Tüm KPI ağacı |
| D2 | "Save" tanımı | Kayıt + clipboard copy | Activation |
| D3 | "Active" tanımı | 7 günde ≥1 gen | WAU baseline |
| D4 | NPS trigger | 30 gün aktif sonra | Cancellation flow |
| D5 | PMF survey trigger | 30 gün aktif | Sean Ellis test |
| D6 | Analytics tool | PostHog self-host | Cost + privacy |
| D7 | Dashboard cadence | Real-time + weekly digest | Founder ritm |
| D8 | Cohort retention period | D1, D7, D30, D60, D90 | Standard SaaS |
| D9 | Pre-revenue metrik odak | Retention > Revenue | MVP-1/2 |
| D10 | Quality metrik baseline | Halüsinasyon < %2, Citation %100 | AI safety |

---

## 12. Çapraz Referans

```text
WSGAU                          → Discovery: JTBD J1+J3+J6 doğrulama
Free conversion ≥%5            → Pricing: loss leader break-even
LTV/CAC ≥3                     → Unit Economics: tier margin
D7 retention ≥%30              → Risk Register: KS-2 acceptance
Halüsinasyon <%2               → Legal: R-PRD-01 mitigation
Source success ≥%70            → Risk Register: KS-1 acceptance
Cost per gen <$0.01            → Unit Economics: variable cost ceiling
Cancellation reason            → Discovery: persona feedback loop
PMF "very disappointed" ≥%40   → Discovery: validation milestone
WAU/MAU ≥30                    → Pro tier hedef segment
```

---

**Sonuç:** **WSGAU** tek metric olarak organize ediyor — kullanım × kalite kombinasyonu manipülasyon dirençli. KPI ağacı **AARRR + Quality + Operational** olarak 6 ana dal. **Faz-spesifik odak** (MVP-1 activation, MVP-2 retention, MVP-3 revenue) overinvestment'i engelliyor. **Kırmızı alarmlar** sistemin sağlığını anında gösterirken **yeşil sinyaller** kutlama anlarını işaretliyor. **PMF survey eşiği %40** Sean Ellis standartı; bu ölçülmeden Faz 6 (paid launch) yapılmamalı.
