# Nodrat — AI Birim Ekonomisi ve Maliyet Modeli

**Doküman türü:** Unit Economics / Cost Modeling
**Sürüm:** v0.1
**Bağımlılık:** PRD v0.1, IA v0.1, Discovery v0.1, Competitive v0.1
**Hedef:** "Bir kullanıcıya bir ay hizmet vermek bize kaça mal oluyor?" sorusunun yapılandırılmış cevabı + pricing tier'ları için margin doğrulaması.

⚠️ **Not:** Bu doküman 2026-Q2 itibarıyla provider fiyatları üzerinden hesaplanmıştır. Provider fiyatları aylık değişebilir; canlı tracker `/admin/observability/storage` ekranında zorunlu.

---

## 0. Yönetici Özeti

```text
Per-user maliyet projeksiyonu (USD/ay):
  Trial (kayıtsız) :  $0.02–$0.05    (1 üretim/gün × 30 gün max)
  Free user        :  $0.10–$0.25    (10 üretim/ay)
  Starter ($8)     :  $0.50–$1.50    (100 üretim/ay)
  Pro ($24)        :  $2.50–$5.00    (500 üretim/ay)
  Agency ($80)     :  $10–$25        (2.500 üretim/ay × 3 koltuk)

Shared cost (tüm kullanıcılar paylaşır):
  Embedding (haber havuzu)   : ~$15–40/ay (50 kaynak)
  Agenda card generation     : ~$8–20/ay
  VPS + storage              : ~$25–60/ay (4 vCPU, 16GB, 500GB SSD)
  Backup off-server          : ~$5–10/ay
  Total shared (sabit)       : ~$53–130/ay

Hedef gross margin:   %75 (her tier'da bireysel)
Break-even paid count: ~25 Starter VEYA ~7 Pro (shared cost'ı amorti için)
Profit unit: Pro tier (gross margin $19–21/ay, en yüksek $/MB)
```

---

## 1. Modelleme Metodolojisi

### 1.1 Maliyet kalemleri

```text
Variable (kullanıcı başına):
  V1. LLM generation (query plan + content gen)
  V2. Embedding (kullanıcı sorgusu + ilgili reranking)
  V3. Provider request overhead (API calls)

Shared (tüm kullanıcılar):
  S1. Haber embedding (kaynaklar × haber × chunk × token)
  S2. Agenda card LLM (event cluster başına)
  S3. VPS compute + storage
  S4. Görsel storage (MinIO disk)
  S5. Database storage (PostgreSQL + pgvector)
  S6. Backup storage
  S7. Bandwidth (ucuz, ihmal edilebilir <10GB/ay)

Fixed (operasyonel, ürünle ölçeklenmez):
  F1. Domain + DNS
  F2. SSL (Let's Encrypt = $0)
  F3. Email (Postmark/Resend ~$10/ay)
  F4. Monitoring (Better Uptime free tier)
  F5. Analytics (Plausible self-hosted = VPS ile dahil)
```

### 1.2 Token model varsayımları

```text
1 Türkçe karakter ≈ 0.4–0.6 token
1 Türkçe paragraf (~150 word) ≈ 250 token
1 haber tam metin ≈ 800–1.500 token
1 chunk (PRD §2.3 ideal 400–700 token) ≈ 500 token avg
1 X paylaşımı (250 char) ≈ 70 token
1 X thread (10 tweet) ≈ 700 token
1 agenda card output ≈ 300 token
1 query plan output ≈ 100 token
```

### 1.3 Provider fiyatları (2026-Q2, USD per 1M tokens)

```text
LLM (chat completion):
  Provider                         Input    Output   Notes
  ─────────────────────────────────────────────────────────────
  DeepSeek V3 via NIM             FREE     FREE     Default, NIM ücretsiz tier (#109)
  DeepSeek V3 native API          $0.27    $1.10    Faz 6+ alternatif (billing)
  OpenRouter Llama 3.3 70B        $0.30    $0.40    Fallback
  Claude Haiku 4.5                $1.00    $5.00    Premium tier
  Claude Sonnet 4.6               $3.00    $15.00   Sadece comparison mode
  GPT-4o-mini                     $0.15    $0.60    Alt fallback
  Local Llama 3.1 8B (vLLM)       Compute  Compute  ~$0.05 ekv. (GPU varsa)

NOT: MVP-1'de DeepSeek V3 NIM endpoint üzerinden ÜCRETSİZ çalışıyor (#109).
Yukarıdaki $0.27/$1.10 native DeepSeek API rate'leri Faz 6+'da NIM
fair-use limitine ulaşılırsa devreye girer.

Embedding:
  Nvidia NIM bge-m3               Free*    -        MVP'de ücretsiz endpoint
  OpenAI text-embedding-3-small   $0.02    -        $0.02 / 1M token
  Voyage 3-large                  $0.06    -        En kaliteli, pahalı
  Local bge-m3 (CPU)              Compute  -        ~$0/token (yavaş)

Rerank (opsiyonel):
  Cohere rerank-v3                $1.00 per 1K queries
  Local cross-encoder             Compute  -        İlk MVP'de skip
```

⚠️ Free* tier limit: NIM bge-m3 prototype 5K req/dk. Üretimde local fallback şart.

---

## 2. Shared Cost — Haber Havuzu Maliyeti

### 2.1 Embedding maliyeti (haber → vector)

```text
Varsayımlar:
  Aktif kaynak sayısı       : 50 (MVP-1: 3, hedef: 50 hafta-12'de)
  Kaynak başına haber/gün   : 50–150 (RSS+kategori karışık)
  Toplam haber/gün          : ~5.000 (50 × 100 ortalama)
  Haber başına chunk        : ~3 (avg 1.500 token / 500 chunk)
  Token/chunk               : 500
  Toplam token/gün          : 5.000 × 3 × 500 = 7.500.000 token

Fiyat (NIM bge-m3 free tier):
  Aylık embedding maliyeti  : $0 (free quota içinde)
  Free tier aşılırsa local  : ~$30/ay (CPU compute marjinal)
  OpenAI'a düşersek         : 7.5M × 30 × $0.02 = ~$4.50/ay 

Karar: NIM free + local bge-m3 fallback. Görece ucuz.
```

### 2.2 Agenda card LLM maliyeti

```text
Varsayımlar:
  Event cluster sayısı       : ~200/gün (haberlerin %4'ü yeni event)
  Card başına input token    : 2.000 (3–5 haber özeti + meta)
  Card başına output token   : 300
  
Aylık çağrı: 200 × 30 = 6.000 agenda card

DeepSeek V3 ile:
  Input cost  : 6.000 × 2.000 × $0.27/1M = $3.24/ay
  Output cost : 6.000 × 300 × $1.10/1M   = $1.98/ay
  Toplam      : ~$5.22/ay

Claude Haiku 4.5 ile (kalite hedef yüksekse):
  Input cost  : 6.000 × 2.000 × $1.00/1M = $12/ay
  Output cost : 6.000 × 300 × $5.00/1M   = $9/ay
  Toplam      : ~$21/ay

Karar: DeepSeek V3 (default), Haiku premium tier'lara
```

### 2.3 Storage maliyeti

```text
PostgreSQL (haber metni + chunks + embeddings):
  Haber: 5.000/gün × 30 gün × 365 = 1.8M haber/yıl
  Tahmini DB boyutu Yıl 1: ~80 GB
  
MinIO (görseller + raw HTML snapshots):
  Görsel: 5.000 haber × 1.5 ortalama × 200KB = ~1.5 GB/gün = 45 GB/ay
  Yıl 1 sonu: ~500 GB
  
Backup off-server (S3 compatible):
  Aylık snapshot: ~100 GB sıkıştırılmış
  Maliyet (Backblaze B2): $0.005/GB = $0.50/ay (ufak)
  Wasabi: $5.99 sabit, üst limitsiz pratik

VPS dahil olduğu için ek yok.
```

### 2.4 VPS operasyonel maliyet

```text
MVP (PRD §6.2):
  Hetzner CCX23: 4 vCPU, 16GB RAM, 240GB NVMe → €23/ay = ~$25/ay
  Hetzner Storage Box (500GB): €4/ay = ~$4/ay
  Toplam: ~$29/ay

Ölçek (Yıl 1 hedef):
  Hetzner CCX43: 8 vCPU, 32GB, 500GB NVMe → €52/ay = ~$57/ay
  Storage Box (1TB): €8/ay = ~$9/ay
  Toplam: ~$66/ay

Diğer:
  Domain                   : $15/yıl = $1.25/ay
  Email (Resend free 3K)   : $0/ay (free tier)
  Backup (B2 100GB)        : $0.50/ay
  Monitoring (free tier)   : $0/ay
```

### 2.5 Toplam shared cost (sabit ve değişken karışık)

```text
MVP fazında (50 kaynak hedefi öncesi):
  VPS:                        $29/ay
  Embedding (haber):           $0/ay (NIM free)
  Agenda LLM (DeepSeek):       $5.22/ay
  Storage backup:              $0.50/ay
  Email + domain:              $1.25/ay
  ──────────────────────────────────
  Toplam:                      ~$36/ay

Ölçek fazında (50 kaynak, 100K haber/ay):
  VPS:                        $66/ay
  Embedding:                  $0–30/ay (free → local fallback)
  Agenda LLM:                 $25–50/ay
  Storage:                    $5/ay
  Email:                      $10/ay (paid email tier)
  Misc:                       $4/ay
  ──────────────────────────────────
  Toplam:                     ~$110–170/ay
```

---

## 3. Variable Cost — Kullanıcı Üretim Maliyeti

### 3.1 Tek bir generation request maliyeti (ortalama)

```text
Akış (PRD §3.3):
  1. Query Planner LLM çağrısı
       Input  : ~200 token (kullanıcı talebi + system prompt)
       Output : ~100 token (structured JSON)
  
  2. Retrieval (embedding + vector search)
       Embedding query: ~50 token
       Vector search: 0 token (local DB query)
  
  3. Content Generator LLM çağrısı
       Input  : ~3.000 token (5 agenda card + plan + system prompt)
       Output : ~700 token (5 X post veya 1 thread)
  
  Toplam input  : ~3.250 token
  Toplam output : ~800 token

DeepSeek V3 (default):
  Input  : 3.250 × $0.27/1M = $0.000878
  Output : 800 × $1.10/1M    = $0.000880
  Per generation cost: ~$0.0018 (~$0.002 yuvarla)

Claude Haiku 4.5 (premium):
  Input  : 3.250 × $1.00/1M = $0.0033
  Output : 800 × $5.00/1M    = $0.0040
  Per generation cost: ~$0.0073 (~$0.008 yuvarla)

Embedding query (NIM free): $0
```

### 3.2 Per-user/month maliyet (kullanım × per-gen cost)

| Tier | Üretim/ay | Provider | Per-gen | Aylık LLM |
|---|---|---|---|---|
| Trial (kayıtsız) | ~10 (1/gün × 10 gün avg) | DeepSeek | $0.002 | $0.02 |
| Free | 10 | DeepSeek | $0.002 | $0.02 |
| Starter | 100 | DeepSeek | $0.002 | $0.20 |
| Pro | 500 | DeepSeek + Haiku karışık | $0.005 ort | $2.50 |
| Agency (3 seat) | 2.500 toplam | Haiku premium | $0.008 | $20.00 |

```text
Notlar:
  - Free user'lar büyük çoğunlukla quota'yı kullanmaz (~%30 utilization)
  - Pro tier %50 DeepSeek, %50 Haiku dağılımı varsayımı
  - Agency tier premium model default, daha uzun context (comparison)
  - Trial 1/gün × 30 gün = 30 üretim teorik, gerçekte ~10
```

### 3.3 Hassasiyet analizi (sensitivity)

```text
Pro tier ($24 fiyat) için per-user maliyet:

Senaryo                               Maliyet/ay    Margin    Margin %
──────────────────────────────────────────────────────────────────────
Düşük kullanım (250 gen, DeepSeek)    $0.50         $23.50    98%
Avg kullanım (500 gen, %50 mix)        $2.50         $21.50    90%
Yüksek kullanım (500 gen, Haiku)       $4.00         $20.00    83%
Aşırı kullanım (quota dolu, Haiku)     $5.00         $19.00    79%
Comparison mode ağır (Sonnet)          $12.00        $12.00    50% ⚠️

Karar: Comparison mode'da Sonnet kullanımı sadece Agency'de açık olmalı.
       Pro tier comparison için Haiku zorla.
```

---

## 4. Provider Karşılaştırması ve Seçim

### 4.1 Provider matrisi

| Provider | Use case | Pros | Cons | Karar |
|---|---|---|---|---|
| **DeepSeek V3** | Default LLM | %95 ucuz, Türkçe iyi, hızlı | API stability orta | ✅ Default |
| OpenRouter | Fallback | Tek API key, çok model | Markup %5-15 | ✅ Fallback |
| Claude Haiku 4.5 | Premium | Türkçe en iyi, güvenilir | Pahalı | ✅ Premium tier |
| Claude Sonnet 4.6 | Sadece Agency comparison | En kaliteli | Çok pahalı | ⚠️ Agency only |
| GPT-4o-mini | Yedek fallback | Kaliteli, makul fiyat | Türkçe orta | ⚠️ Backup only |
| NIM bge-m3 | Embedding | Free tier | Quota limit | ✅ Default |
| Local bge-m3 (CPU) | Embedding fallback | $0, sınırsız | Yavaş | ✅ Fallback |
| Voyage embeddings | Premium embedding | En kaliteli | Pahalı | ❌ MVP'de yok |

### 4.2 Routing stratejisi (tier × provider)

```text
Trial:
  query_plan        → DeepSeek V3
  content_generator → DeepSeek V3
  embedding         → NIM (local fallback)

Free:
  query_plan        → DeepSeek V3
  content_generator → DeepSeek V3
  embedding         → NIM

Starter ($8):
  query_plan        → DeepSeek V3
  content_generator → DeepSeek V3 (default), OpenRouter Llama (fallback)
  embedding         → NIM

Pro ($24):
  query_plan        → DeepSeek V3
  content_generator → Haiku 4.5 default
  comparison mode   → Haiku 4.5 (Sonnet kapalı)
  embedding         → NIM

Agency ($80):
  query_plan        → DeepSeek V3 (planner'da kalite kritik değil)
  content_generator → Haiku 4.5 default, Sonnet 4.6 comparison'da
  embedding         → Voyage 3-large opsiyonel
```

### 4.3 Provider failover

```text
LLM failover sırası:
  1. Default (DeepSeek/Haiku tier'a göre)
  2. OpenRouter aynı model
  3. GPT-4o-mini fallback (kalite düşüşü kabul)
  4. Hata → kullanıcıya gecikme bildirimi

Embedding failover:
  1. NIM bge-m3
  2. Local bge-m3 (CPU, yavaş ama devam eder)
  3. OpenAI embedding-3-small
  4. Hata → embedding kuyruğunda biriktir, retry
```

---

## 5. Margin Hesaplaması

### 5.1 Her tier için brüt margin

```text
Tier        Fiyat/ay   Maliyet/ay   Brüt Margin   Margin %
─────────────────────────────────────────────────────────────
Trial       $0          $0.05        -$0.05        N/A (loss leader)
Free        $0          $0.15        -$0.15        N/A (loss leader)
Starter     $8          $1.00        $7.00         87%
Pro         $24         $3.50        $20.50        85%
Agency      $80         $18.00       $62.00        77%

Hedef gross margin: ≥75% her paid tier'da → ✅ tüm tier'lar geçiyor
```

### 5.2 Free tier loss leader analizi

```text
Free user maliyeti: ~$0.15/ay (10 üretim × DeepSeek)

Conversion hedefi:
  Free → Starter: %5 (sektör avg %2-7)
  Free → Pro:     %1
  
Break-even:
  100 free user × $0.15 = $15/ay loss
  Starter conversion: 5 × $7 margin = $35
  Pro conversion:     1 × $20.50 margin = $20.50
  
  Net: $35 + $20.50 - $15 = $40.50 / 100 free user
  → %5 conversion @ Starter tek başına break-even sağlar ✅
```

### 5.3 Break-even analizi (shared cost amorti)

```text
MVP fazı shared cost: $36/ay
Ölçek fazı shared cost: $150/ay (avg)

Senaryo A — sadece Starter:
  Margin per user: $7
  MVP break-even: 36/7 = 6 paid Starter
  Ölçek break-even: 150/7 = 22 paid Starter

Senaryo B — sadece Pro:
  Margin per user: $20.50
  MVP break-even: 36/20.50 = 2 paid Pro
  Ölçek break-even: 150/20.50 = 8 paid Pro

Senaryo C — gerçekçi mix (60% Starter, 30% Pro, 10% Agency):
  Avg margin: 0.6*7 + 0.3*20.50 + 0.1*62 = $16.55
  MVP break-even: 36/16.55 = ~3 paid users
  Ölçek break-even: 150/16.55 = ~10 paid users
```

---

## 6. Maliyet Kontrolleri ve Alarmları

### 6.1 Sistem-seviye kontroller

```text
C1. Provider başına aylık quota cap
    DeepSeek max: $200/ay
    Claude max:    $300/ay
    OpenAI max:    $50/ay (sadece fallback)
    Cap aşılırsa  → routing düşük tier'a düşer

C2. Per-user concurrency limit
    Free: 1 concurrent generation
    Starter: 2
    Pro: 3
    Agency: 5 per seat

C3. Per-user rate limit (saatlik)
    Free: 5/saat
    Starter: 20/saat
    Pro: 60/saat
    Agency: 120/saat per seat

C4. Embedding batch processing
    Tek tek değil 100'lük batch
    %80 cost reduction overhead'ten

C5. Aggressive caching
    Query plan cache (similar queries)
    Embedding cache (popular queries)
    Agenda card cache (24h TTL)

C6. Token limit per request
    Input: max 8K token (context cap)
    Output: max 1.5K token (X format yeterli)
```

### 6.2 Alarm eşikleri

```text
Daily provider spend > $20      → Slack alarm
Single user spend > $5/gün       → Block + admin review
Embedding queue > 5K bekleyen   → Local fallback'e geç
Cache hit rate < %30            → Cache logic incele
Per-user margin < %50           → Routing düşür / tier yükselt teklif
Cost per generation > $0.05     → Provider routing audit
```

### 6.3 Aylık cost audit checklist

```text
[ ] Provider invoice'ları VPS bütçesi vs
[ ] Per-user gerçek maliyet hesabı (top 20 power user)
[ ] Free → paid conversion oranı
[ ] Cache hit rate trendi
[ ] Embedding storage growth rate
[ ] Backup retention policy uygulanıyor mu
[ ] Dead letter queue temizliği
[ ] Görsel storage growth (MinIO)
```

---

## 7. Faz Bazlı Maliyet Projeksiyonu

```text
Faz 0–1 (3 kaynak, no users):
  VPS:                  $29/ay
  Embedding:            $0
  Agenda LLM:           $0.50/ay (3 kaynak çok az event)
  Total:                ~$30/ay
  Burn rate Yıl 1:      ~$360

Faz 2 (10 kaynak, 50 kullanıcı):
  VPS:                  $29/ay
  Embedding:            $0–5/ay
  Agenda LLM:           $5/ay
  User generations:     50 × $0.30 = $15/ay
  Total:                ~$55/ay

Faz 3 (25 kaynak, 500 kullanıcı):
  Mix: 80% free, 18% Starter, 2% Pro
  VPS:                  $66/ay (upgrade)
  Embedding:            $5/ay
  Agenda LLM:           $15/ay
  User generations:
    400 free × $0.15  = $60
    90 Starter × $1   = $90
    10 Pro × $3.50    = $35
  Total cost:           ~$271/ay
  
  Revenue:
    90 × $8           = $720
    10 × $24          = $240
  Total revenue:        $960
  
  Net margin:           $689 (~%72)

Ölçek (50 kaynak, 5K kullanıcı, %30 paid):
  Total cost:           ~$2.500/ay
  Total revenue:        ~$15.000/ay
  Net margin:           ~$12.500/ay (~%83)
```

---

## 8. Karar Noktaları

| ID | Karar | Önerim | Etki |
|---|---|---|---|
| D1 | Default LLM provider | DeepSeek V3 | Tüm Free/Starter |
| D2 | Premium model | Haiku 4.5 | Pro/Agency tier |
| D3 | Comparison mode için Sonnet aç mı? | Sadece Agency | Margin koruması |
| D4 | Embedding self-host mu? | NIM free + local fallback | $0 baseline |
| D5 | Free tier kullanım limiti | 10 üretim/ay | Loss leader, %5 conv hedefi |
| D6 | Yıllık iskonto | 2 ay bedava (16.7%) | Cash flow + retention |
| D7 | Provider quota cap aktif mi? | Evet, hard cap | Cost runaway koruması |
| D8 | Cache TTL agenda card | 24 saat | Cost reduction |
| D9 | Local LLM (vLLM) ne zaman? | 1.000+ paid sonra GPU değer | Faz 7+ |

---

## 9. Çapraz Referans

```text
Per-gen cost $0.002–0.008      → Pricing Strategy: tier maliyet doğrulama
Free tier $0.15/mo             → Pricing Strategy: %5 conversion break-even
Pro margin %85                 → Pricing Strategy: anchor doğrulama
Provider routing tablosu       → API Contracts: model_providers entity
Cache stratejisi               → IA §7.4 (Faz 7 caching)
Cost alarm eşikleri            → Success Metrics: operasyonel KPI
Comparison mode Sonnet kapalı  → MVP Cut-list: Faz 2 scope
NIM embedding (free)           → Risk Register: provider lock-in
```

---

**Sonuç:** Mevcut provider fiyatları altında **%75+ gross margin tüm paid tier'larda gerçekçi**. En büyük risk DeepSeek API stability ve NIM free tier'ın değişmesi. Her ikisinde de fallback hazır (OpenRouter + local bge-m3). Pro tier en yüksek $/MB veriyor — **GTM odağı Pro tier olmalı**, Starter "merdiven", Agency niş upside. Free tier %5 conversion ile break-even, sürdürülebilir loss leader.
