# Nodrat — AI Birim Ekonomisi ve Maliyet Modeli

**Doküman türü:** Unit Economics / Cost Modeling
**Sürüm:** v0.3 (2026-05-08 — Lemon Squeezy MoR ~%5+50¢ payment fee margin recalc, Epic [#448](https://github.com/selmanays/nodrat/issues/448))
**Bağımlılık:** PRD v0.2, IA v0.1, Discovery v0.1, Competitive v0.1, Pricing Strategy v0.2
**Hedef:** "Bir kullanıcıya bir ay hizmet vermek bize kaça mal oluyor?" sorusunun yapılandırılmış cevabı + pricing tier'ları için margin doğrulaması.

⚠️ **Not:** Bu doküman 2026-Q2 itibarıyla provider fiyatları üzerinden hesaplanmıştır. Provider fiyatları aylık değişebilir; canlı tracker `/admin/observability/storage` ekranında zorunlu.

> **v0.3 değişikliği (2026-05-08):** Payment provider Iyzico'dan **Lemon Squeezy MoR**'a (Epic #448). LS komisyonu **~%5 + 50¢** (Iyzico ~%2.5 yerine). Bu LS'nin global tax compliance + chargeback + customer portal hosted yönetiminin maliyetidir. **Margin hedefi %75'ten %70'e revize**. Net revenue per tier: Starter $8 → ~$7.10, Pro $24 → ~$22.30, Agency $79 → ~$74.55. Per-user variable cost değişmedi (LLM/embedding tarafı aynı). Payment fee artışı per-user basis'te değil, revenue-side; net margin matematiği §3.2'de güncellendi.

> **v0.2 değişikliği**: §2.4.1 yeni bölüm — 1000 kullanıcı / 1400 RSS hedef
> ölçeği için runway projeksiyonu (storage 18-24 ay, NIM kullanım profili,
> local model footprint, ölçek genişletme stratejisi). MVP-1.4 process &
> discard mimarisi + MVP-1.5 local primary + storage optimization sonrası.

---

## 0. Yönetici Özeti

```text
Per-user maliyet projeksiyonu (USD/ay):
  Anonim search    :  $0.00          (#261 Search-as-a-Service, sadece DB query)
  Free user        :  $0.10–$0.25    (10 üretim/ay)
  Starter trial    :  $0.05–$0.15    (3 gün × prorated ~10 gen, sonra paid charge)
  Starter ($8)     :  $0.50–$1.50    (100 üretim/ay)
  Pro trial        :  $0.20–$0.50    (3 gün × prorated ~50 gen)
  Pro ($24)        :  $2.50–$5.00    (500 üretim/ay)
  Agency trial     :  $1.50–$3.50    (7 gün × prorated ~580 gen)
  Agency ($79)     :  $10–$25        (2.500 üretim/ay × 3-10 koltuk)

Payment provider fee (Lemon Squeezy MoR, %5 + 50¢ per transaction):
  Starter $8       :  -$0.90         ($8 × 0.05 + $0.50 = $0.90, %88.75 retain)
  Pro $24          :  -$1.70         ($24 × 0.05 + $0.50 = $1.70, %92.92 retain)
  Agency $79       :  -$4.45         ($79 × 0.05 + $0.50 = $4.45, %94.37 retain)
  Agency $129 (5)  :  -$6.95
  Agency $249 (10) :  -$12.95

Shared cost (tüm kullanıcılar paylaşır):
  Embedding (haber havuzu)   : ~$0/ay (local bge-m3, MVP-1.5 sonrası)
  Agenda card generation     : ~$8–20/ay (DeepSeek native API)
  VPS + storage              : ~$25/ay (Contabo VPS 40 + Object Storage)
  Backup off-server          : included (Contabo OS)
  Total shared (sabit)       : ~$33–45/ay

Hedef gross margin:   %70 (her tier'da bireysel — LS fee dahil; eski %75 Iyzico pre-pivot)
Break-even paid count: ~6 Pro VEYA ~50 Starter (shared cost'ı amorti için)
Profit unit: Pro tier (gross margin $19–20/ay net, en yüksek $/MB)

Net revenue tablosu (LS fee sonrası):
  Tier             Gross  - LS fee  = Net
  ────────────────────────────────────────
  Starter $8       $8.00  - $0.90   = $7.10
  Pro $24          $24.00 - $1.70   = $22.30
  Agency $79       $79.00 - $4.45   = $74.55
  Agency $129      $129   - $6.95   = $122.05
  Agency $249      $249   - $12.95  = $236.05

Önemli: LS MoR sayesinde Limited Şti. + e-Arşiv + muhasebe fixed cost
(~$50-100/ay ek) yok. Bu fee artışını büyük ölçüde dengeler.
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
PostgreSQL (haber metni + chunks + embeddings + image metadata):
  Haber: 5.000/gün × 30 gün × 365 = 1.8M haber/yıl
  Görsel metadata (#304): 1.8M × 1.5 ort. × 1KB ~= 2.7 GB/yıl
  Tahmini DB boyutu Yıl 1: ~85 GB

MinIO (sadece raw HTML snapshot — #304 ile görsel storage iptal):
  HTML snapshot: 5.000 × 50KB = 250 MB/gün = 7.5 GB/ay = 90 GB/yıl
  Görsel: 0 (process & discard, NIM VLM metadata extraction sonrası
          bytes silinir — eski plan 500 GB/yıl idi, %98 azalma)

Backup off-server (S3 compatible):
  Aylık snapshot: ~10-15 GB sıkıştırılmış (önceki ~100 GB'dan azalma)
  Maliyet (Backblaze B2): $0.005/GB = $0.05-0.10/ay
  Wasabi: $5.99 sabit, üst limitsiz pratik

VPS dahil olduğu için ek yok. NIM VLM API: free tier 40 RPM
(5K haber/gün × 1.5 görsel = 7.500 call/gün = ~5 RPM ortalama
ama burst için worker concurrency 2; quota'ya sığar).
```

### 2.4 VPS operasyonel maliyet

**v1.0 (MVP-1)** — Hetzner referans (planlanmış, gerçekleşmedi):
```text
Hetzner CCX23: 4 vCPU, 16GB RAM, 240GB NVMe → €23/ay
Storage Box (500GB): €4/ay
Toplam: ~€27 (~$29/ay)
```

**v1.1 (MVP-1 fiili)** — Contabo shared VPS (mevcut, ortak başka projelerle):
```text
Contabo VPS (ortak): paylaşımlı, app-spesifik maliyet ~$8/ay (orantı)
Backblaze B2 backup: $0.50/ay
Toplam: ~$9/ay (geçici, sınırlı)
```

**v1.2 (MVP-1.5 — Epic #215, ✅ delivered 2026-05-06)** — Contabo dedicated:
```text
Contabo Cloud VPS 40 NVMe: 12 vCPU / 47 GB / 484 GB NVMe
  Hub Europe, 12-month term: $36/ay (~€33)
  + NVMe Storage Extension: $5.70/ay (~€5.20)
  Toplam VPS: ~$41.70/ay = €38.20/ay
Contabo Object Storage 250 GB: €2.49/ay = ~$2.70/ay
  → 32 TB egress dahil (restore drill ücretsiz)
Toplam: ~$44.40/ay = ~€40.70/ay = ~€488/yıl
```

> **2026-05-03 plan değişikliği:** VPS 30 → VPS 40. MVP-1.1 Tour 5 sonrası
> reranker self-host (BGE-reranker-v2-m3 ~11 GB FP32) + ileride embedding
> self-host ihtiyacı VPS 30'un (24 GB) sınırını zorluyordu. VPS 40 sweet spot.

**v2.0 (MVP-2 / 25 kaynak ölçeği)** — aynı VPS, OS upgrade:
```text
Cloud VPS 40 NVMe (same): $41.70/ay
Contabo OS 500 GB: €4.98/ay
Toplam: ~$47/ay
```

**v3.0 (MVP-3 / 50 kaynak + paid users)** — VPS sabit:
```text
Cloud VPS 40 (yeterli, MVP-3'e kadar): $41.70/ay
Contabo OS 1 TB: €9.96/ay
Opsiyonel GPU server (Hetzner GEX44 RTX 4000): €184/ay
Toplam (GPU yok): ~$53/ay
Toplam (GPU var): ~€220/ay (sadece custom LLM gerekirse)
```

Diğer:
```text
Domain                   : $15/yıl = $1.25/ay
Email (Resend free 3K)   : $0/ay (free tier)
Monitoring (free tier)   : $0/ay
```

> **Not** (MVP-1.5'ten itibaren): Backblaze B2 → Contabo Object Storage geçişi
> hem maliyet hem operasyonel kolaylık için yapıldı. Contabo OS aynı sağlayıcı
> içinde olduğu için VPS↔Storage transfer hızlı ve ücretsiz; 32 TB egress
> sürpriz fatura riskini kaldırır.

### 2.4.1 Kapasite analizi — 1000 kullanıcı / 1400 RSS senaryosu

> Bu bölüm MVP-1.4 sonrası altyapı (process & discard image pipeline + local
> bge-m3/reranker primary + NIM VLM/fallback) ile hedef ölçek için runway
> projeksiyonudur. Kaynak: 2026-05-06 production smoke + capacity planning.

#### Veri akışı

| Kalem | Hedef ölçek (1000 user / 1400 RSS) |
|---|---|
| Article girişi | 1400 source × 20 article/gün = **28K/gün** |
| Yıllık article | **10.2M** |
| Image extraction | 28K × 1.5 image = **42K/gün** |
| Generation | 1000 user × 5/hafta = **715/gün** |

#### Storage projeksiyonu (MVP-1.5 sonrası: body_html drop + cold tier + binary quantization)

| Layer | 1 yıl | 2 yıl | Yer |
|---|---|---|---|
| `articles` (body_html drop sonrası) | 51 GB | 102 GB | DB hot |
| `article_chunks` (binary quant 8x) | 25 GB | 50 GB | DB hot |
| `article_images` metadata | 7.5 GB | 15 GB | DB hot |
| `agenda_cards`, `event_clusters`, RAPTOR | 10 GB | 20 GB | DB hot |
| Diğer (users, generations, audit) | 5 GB | 10 GB | DB hot |
| **DB hot toplam** | **~100 GB** | **~200 GB** | VPS NVMe 250 GB |
| Cold tier (raw_html 30+gün) | 42 GB | 84 GB | Contabo OS |
| DB backup (aylık snapshot) | 60 GB | 120 GB | Contabo OS |
| **Contabo OS toplam** | **~100 GB** | **~200 GB** | OS 250 GB |

#### Local model footprint (bge-m3 + bge-reranker-v2-m3, MVP-1.5 PR-8/PR-9)

CPU-only inference (Contabo VPS 40 GPU yok). ONNX Runtime FP16, batch=32:

| Model | Param | RAM resident | Disk | CPU throughput |
|---|---|---|---|---|
| `bge-m3` (embedding) | 567M | 1.5 GB | 2.5 GB | ~30-50 chunk/sn |
| `bge-reranker-v2-m3` | 568M | 1.5 GB | 2.5 GB | ~20-30 pair/sn |
| ONNX overhead | — | 0.5 GB | — | — |
| **Toplam** | | **3.5 GB** | **5 GB** | **~1 vCPU effective** |

Günlük yük (1000 user / 1400 RSS):
- Embedding: 140K chunk/gün → **~78 dk/gün ortalama compute** (burst 2-3 saat)
- Reranker: 53K pair/gün → **~30 dk/gün compute**
- Toplam: ~1 vCPU equivalent / 12 vCPU (yıllık compute %8)

Latency karşılaştırma:
- Local CPU: 50-200 ms (deterministic, NIM outage riski yok)
- NIM: 1-2 saniye (network + rate limit)

#### Bottleneck'ler ve runway

| Sınır | 1000 user / 1400 RSS | Runway |
|---|---|---|
| **VPS NVMe 250 GB** | DB ~100 GB/yıl, ~110 GB buffer | **~18-24 ay** ✅ |
| **NIM rate limit (40 RPM)** | Sadece VLM kullanır (embedding+rerank local) → 30 RPM ortalama | **2500-3000 source'a kadar rahat** ✅ |
| **Contabo OS 250 GB** | 100 GB/yıl backup + cold tier | **~2.5 yıl** ✅ |
| **VPS RAM 48 GB** | 25 + 3.5 (model'ler) = 28-30 GB | **3500-4000 user'a kadar** ✅ |
| **VPS 12 vCPU** | ~1 vCPU local model'ler + 16 thread workers | **5000+ user'a kadar** ✅ |
| **DeepSeek cost** | 20K gen/ay × ~$0.0016 = ~$33/ay | maliyetsel sınır yok ✅ |

#### MVP-1.5 öncesi vs sonrası (3-4x runway artışı)

| Senaryo | 1400 source / 1000 user runway |
|---|---|
| **Eski (image storage'lı + NIM tüm pipeline)** | **6 ay** (5 TB/yıl image → VPS dolu, NIM rate limit bottleneck) |
| **Yeni (process & discard + local primary + MVP-1.5 storage opt.)** | **18-24 ay** |

#### Ölçek genişletme stratejisi (24+ ay sonrası)

Bottleneck sırasıyla:
1. **24. ay**: VPS NVMe %80-90 doluyorsa
   - Article retention 365 → 180 gün (eski haberler nadiren kullanılıyor)
   - Veya VPS upgrade: Contabo VPS 80 (24 vCPU/96 GB/500 GB NVMe ~€40/ay)
2. **3000+ source**: VLM rate limit
   - NIM Pro tier (pricing TBD)
   - Hetzner GPU instance (RTX 4000 ~€100-200/ay) self-hosted Llama 4 Vision
   - Veya Claude Haiku Vision (Pro tier kullanıcılarına, ~$42/ay × 42K img)
3. **4000+ user**: RAM
   - Contabo VPS 80 upgrade (96 GB RAM)

**MRR projeksiyon**: Bu altyapıyla MRR ~$1500-2000/ay (250-500 paid user) yetmesi muhtemel. Sonraki ölçek MRR-justified olur.

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
| Anonim (search-only) | 0 | — | — | $0 |
| Free | 10 | DeepSeek | $0.002 | $0.02 |
| Starter trial (3g) | ~10 prorated | DeepSeek | $0.002 | $0.02 (one-time) |
| Starter | 100 | DeepSeek | $0.002 | $0.20 |
| Pro trial (3g) | ~50 prorated | DeepSeek+Haiku | $0.005 ort | $0.25 (one-time) |
| Pro | 500 | DeepSeek + Haiku karışık | $0.005 ort | $2.50 |
| Agency trial (7g) | ~580 prorated × 3 seat | Haiku premium | $0.008 | $4.50 (one-time) |
| Agency (3 seat) | 2.500 toplam | Haiku premium | $0.008 | $20.00 |

```text
Notlar:
  - Free user'lar büyük çoğunlukla quota'yı kullanmaz (~%30 utilization)
  - Pro tier %50 DeepSeek, %50 Haiku dağılımı varsayımı
  - Agency tier premium model default, daha uzun context (comparison)
  - Trial maliyeti one-time (3-7g period); paid plan'a geçince standart aylık LLM
  - Anonim search (#261) maliyetsiz: sadece embedding query (local CPU) + DB cosine
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
Tier              Fiyat/ay   Maliyet/ay   Brüt Margin   Margin %
─────────────────────────────────────────────────────────────────────
Anonim search     $0          $0           $0            N/A (TOFU funnel)
Free              $0          $0.15        -$0.15        N/A (loss leader)
Starter trial     $0          $0.05*       -$0.05*       N/A (one-time, conversion fee)
Starter (paid)    $8          $1.00        $7.00         87%
Pro trial         $0          $0.25*       -$0.25*       N/A (one-time)
Pro (paid)        $24         $3.50        $20.50        85%
Agency trial      $0          $4.50*       -$4.50*       N/A (one-time, 7g × 3 seat)
Agency (paid)     $80         $18.00       $62.00        77%

* one-time trial cost (3-7g period). Paid plan'a geçen kullanıcı için ARPU > trial cost (1 ay paid = 87-77% margin recover).
Trial cost beklenmesi: %30-40 cancel × marjinal cost = strategic acquisition expense.

Hedef gross margin: ≥75% her paid tier'da → ✅ tüm tier'lar geçiyor (paid state).
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
| D10 | Tüzel kişilik / vergi yapısı (2026-05-08, Epic #448, vergi danışmanı resmi pozisyonu) | **Şahıs ticari kazanç mükellefiyeti** (Limited Şti. defer, $5K MRR plan, $10K convert) | Launch hızı + bürokrasi yok; LS payout şahıs hesabına; kur farkı ticari faaliyet kapsamında |
| D11 | LS payout muhasebe modeli | LS reverse invoice + banka dekontu gelir kayıt; mali müşavirden 4 yazılı teyit (#473) | KDV ihracat istisnası, sınıflandırma, FX kayıt netliği |

---

### 8.1 Tüzel kişilik threshold matrisi (vergi danışmanı resmi pozisyonu — Epic #448)

> **Vergi danışmanı görüşü 2026-05-08:** "Limited şirket için tek bir 'zorunlu MRR eşiği' yok. Vergisel olarak şahıs işletmesiyle başlayıp Limited'i risk, KDV/kurumlar vergisi, giderleşme, yatırım, ekip ve B2B algısı nedeniyle seçersin."

| Eşik | Yıllık | Aksiyon |
|---|---|---|
| 0–$1K MRR | $0–$12K | **Şahıs ticari kazanç işletmesi yeterli** + kayıt düzeni kurulur |
| $1K–$3K MRR | $12K–$36K | Şahıs işletmesi devam, muhasebe disiplini sıkılaştır |
| $3K–$5K MRR | $36K–$60K | **Limited Şti. simülasyonu** (review trigger) — mali müşavirle |
| $5K–$10K MRR | $60K–$120K | **Limited Şti. kuruluş planı başlat** (banka, sözleşme, muhasebe, marka) |
| $10K+ MRR | $120K+ | Limited Şti.'ye **geçiş kuvvetle önerilir** |
| B2B/ajans satışları ağır | MRR'den bağımsız | Limited daha güvenli + profesyonel görünür |

**Operasyonel trigger'lar (MRR'den bağımsız Limited'e geçiş):**
- LS dışında direkt kurumsal fatura isteyen müşteri çıktığında
- Founder dışı ekip/contractor ödemeleri düzenli hale geldiğinde
- Reklam, donanım, yazılım, danışmanlık giderleri ciddi artarsa
- Yatırım, ortaklık veya satış görüşmesi başladığında
- Banka şahıs hesabına gelen USD hacmi açıklama yükü yarattığında

**Vergi danışmanı eşik notu:** Belgelerdeki >$3K MRR review kararı korunur; iç politika olarak **$5K MRR'de Limited kuruluş planı**, **$10K MRR'de Limited'e geçiş**.

**2026 GVK tarifesi (referans, şahıs ticari kazanç):** 190.000 TL'ye %15, 400.000 TL'ye %20, 1.000.000 TL'ye %27, 5.300.000 TL'ye %35, üstü %40. Limited kurumlar vergisi ayrıca + dağıtım stopajı + bordro/idari yük.

**Basit usul DEĞIL:** SaaS/online aboneliği basit usul kapsamında kabul edilmez (klasik küçük esnaf kurgusu için tasarlanmış; 2026 hadleri SaaS'a uygun değil). Gerçek usulde şahıs işletmesi başlangıç noktası.

---

### 8.2 LS Payout Muhasebe Akışı (vergi danışmanı + mali müşavir)

```text
Aylık akış (şahıs ticari kazanç mükellefi):

1. LS payout oluştu
   → LS dashboard'dan reverse invoice indir (PDF arşiv)

2. Bankaya USD geldi (Wise / banka)
   → TCMB döviz alış kuru / mali müşavir tarihli kur ile TL karşılık kayıt
   → Defter: "Yurt dışı yazılım/SaaS satış geliri" hesap kalemine alacak

3. USD hesapta bekledi (kısmi tutmak istersek)
   → Dönem sonu USD bakiye değerleme (mali müşavir kuralı)

4. USD TL'ye çevrildi
   → Kayıtlı TL değer × dönüşen TL aralığında fark = kur farkı geliri/gideri
   → Defter: "Kambiyo karları/zararları" hesabı

5. LS komisyon + chargeback fee
   → Gider olarak kayıt (LS bildirim email + LS dashboard)

6. Banka komisyonu
   → Operasyonel gider

Aylık raporlama (mali müşavire):
  - LS reverse invoice PDF
  - Banka payout dekontu
  - Kur tablosu (TCMB veya muhasebe kuru)
  - LS komisyon kesintisi rapor
  - Chargeback / refund detayı

Yıllık beyan:
  - Şahıs ticari kazanç gelir vergisi (Mart, beyan dönemi)
  - KDV: TR müşteriye KDV beyanı YOK (LS MoR keser).
    LS payout'u için KDV ihracat istisnası uygulaması mali
    müşavirle netleştirilecek (#473 — 4 yazılı teyit).
  - Stopaj: TR'de ödeme alımında stopaj YOK.
```

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
