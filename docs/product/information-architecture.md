# Nodrat — Bilgi Mimarisi (Information Architecture)

**Doküman türü:** Information Architecture (IA)
**Sürüm:** v0.1
**Kaynak PRD:** `product/prd.md` (v0.1)
**Hedef:** Nodrat SaaS platformunun tüm bilgi katmanlarını (kullanıcı rolleri, sayfalar, navigasyon, veri modeli, API, içerik türleri, akışlar) tek bir referansta toplamak. Bu doküman frontend, backend ve UX ekipleri için kanonik haritadır.

---

## 0. Doküman Yol Haritası

```text
1.  Ürün özeti ve mimari prensipler
2.  Kullanıcı rolleri ve yetki matrisi
3.  Üst düzey sistem haritası
4.  Bilgi domainleri (top-level taxonomy)
5.  Sayfa / ekran hiyerarşisi
6.  Navigasyon yapısı
7.  Veri modeli haritası (entity ilişkileri)
8.  API yüzeyi haritası
9.  İçerik türleri ve sözlük (taxonomy + glossary)
10. Kullanıcı akışları (user flows)
11. UI bileşen hiyerarşisi
12. Durum (state) ve hata mimarisi
13. Faz bazlı bilgi haritası (MVP-1 → MVP-6)
14. Çapraz referans matrisleri
```

---

## 1. Ürün Özeti ve Mimari Prensipler

### 1.1 Tek cümle özet

Nodrat, gündemi **kaynaklı X içeriklerine dönüştüren editör odaklı üretim aracıdır**. Admin tarafından kontrol edilen güvenilir haber havuzunu RAG mimarisiyle aranabilir hale getirir; kullanıcının doğal dille yazdığı gündem talebini kaynaklı X paylaşımlarına, özetlere ve karşılaştırmalı analizlere dönüştürür. Self-hosted SaaS.

**Pozisyon (research-driven, 2026-05-01):** "ChatGPT yerine değil, ChatGPT yanında — gündem için özel araç." Nodrat haber kaynağı değildir; üretim ve doğrulama destek aracıdır.

### 1.2 Çekirdek mimari prensipler

```text
P1. Admin-controlled trust: Haber kaynaklarını sadece admin ekler.
P2. RAG-only generation: LLM'e tüm arşiv değil, seçilmiş bağlam verilir.
P3. Provider abstraction: LLM, embedding, ödeme provider'ları değiştirilebilir.
P4. Time-aware retrieval: current / weekly / archive / comparison modları.
P5. Source-cited output: Her üretim kaynak gösterimi taşır.
P6. No hallucination: Veri yetersizse içerik üretilmez.
P7. Admin-verified visual labels: Otomatik kişi tanıma yok; admin onayı esas.
P8. Queue-based scaling: Tek VPS başlangıç, queue ile yatay büyüme.
P9. Self-hosted first: MVP'de ücretli altyapı yok.
P10. Style ≠ truth: Stil profili veri doğruluğunun önüne geçemez.
```

---

## 2. Kullanıcı Rolleri ve Yetki Matrisi

### 2.1 Roller hiyerarşisi

```text
Super Admin / Sistem Yöneticisi
   └── (gelecekte) Editor Admin (opsiyonel sub-role)
Registered User (Free Member)
Registered User (Paid Member)
Guest / Trial User
```

### 2.2 Yetki matrisi

| Yetki Alanı | Super Admin | Paid User | Free User | Guest |
|---|---|---|---|---|
| Haber kaynağı ekleme/silme | ✅ | ❌ | ❌ | ❌ |
| Selector test aracı | ✅ | ❌ | ❌ | ❌ |
| Haber/görsel inceleme (raw) | ✅ | ❌ | ❌ | ❌ |
| Görsel etiketleme | ✅ | ❌ | ❌ | ❌ |
| Entity registry yönetimi | ✅ | ❌ | ❌ | ❌ |
| Model provider config | ✅ | ❌ | ❌ | ❌ |
| Queue & worker izleme | ✅ | ❌ | ❌ | ❌ |
| Plan/paket yönetimi | ✅ | ❌ | ❌ | ❌ |
| Gündem talebi yazma | ✅ | ✅ | ✅ | ✅ (sınırlı) |
| Tüm zaman modları | ✅ | ✅ | partial | current only |
| Stil profili oluşturma | ✅ | ✅ | ❌ | ❌ |
| Görsel destekli içerik | ✅ | ✅ | ❌ | ❌ |
| Üretim geçmişi saklama | ✅ | ✅ | ✅ (sınırlı) | ❌ |
| Kaynak detayı görüntüleme | full | full | full | partial |
| Premium model erişimi | ✅ | ✅ | ❌ | ❌ |

---

## 3. Üst Düzey Sistem Haritası

```text
                    ┌───────────────────────────────────┐
                    │         NODRAT PLATFORMU          │
                    └─────────────────┬─────────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
   ┌────▼────┐                  ┌─────▼─────┐                 ┌─────▼─────┐
   │ ADMIN   │                  │   USER    │                 │  PUBLIC   │
   │ DOMAIN  │                  │  DOMAIN   │                 │  DOMAIN   │
   └────┬────┘                  └─────┬─────┘                 └─────┬─────┘
        │                             │                             │
   ┌────▼────────────┐         ┌──────▼──────────┐          ┌──────▼──────┐
   │ Kaynak Yönetimi │         │ Gündem Talebi   │          │ Landing     │
   │ Haber Yönetimi  │         │ İçerik Üretimi  │          │ Auth        │
   │ Görsel Yönetimi │         │ Geçmiş          │          │ Pricing     │
   │ Entity/Etiket   │         │ Stil Profili    │          │ Trial       │
   │ RAG Operasyon   │         │ Ayarlar         │          │ Legal       │
   │ Queue Operasyon │         └─────────────────┘          └─────────────┘
   │ Plan/Billing    │
   │ Observability   │
   │ Settings        │
   └─────────────────┘

                              ▲                  ▲
                              │                  │
                      ┌───────┴──────────────────┴──────┐
                      │     PAYLAŞILAN ÇEKIRDEK         │
                      │  - Provider katmanı             │
                      │  - Queue & worker'lar           │
                      │  - PostgreSQL + pgvector        │
                      │  - MinIO (görsel/snapshot)      │
                      │  - Scheduler                    │
                      │  - Observability                │
                      └─────────────────────────────────┘
```

---

## 4. Bilgi Domainleri (Top-Level Taxonomy)

```text
Nodrat
├── 1. Identity & Access            (auth, sessions, roles)
├── 2. Source Management            (RSS, category page, manual)
├── 3. Article Pipeline             (discover → fetch → clean → archive)
├── 4. Media & Visual Intelligence  (download, hash, VLM, OCR, labels)
├── 5. Entity Knowledge             (persons, orgs, locations, topics)
├── 6. RAG Layer                    (chunks, embeddings, clusters, agenda cards)
├── 7. Content Generation           (query plan, retrieval, LLM output)
├── 8. Style Cloning                (profiles, samples, applications)
├── 9. Billing & Plans              (plans, subscriptions, usage)
├── 10. Operations                  (queue, scheduler, healthchecks)
├── 11. Observability               (metrics, logs, audit)
├── 12. Configuration               (providers, limits, system settings)
└── 13. Legal & Compliance          (TOS, KVKK, scraping ethics)
```

Her domain → 5. bölümdeki bir veya birden fazla sayfa kümesi ile, 7. bölümdeki bir veya birden fazla entity ile, 8. bölümdeki bir veya birden fazla API endpoint grubu ile eşleşir.

---

## 5. Sayfa / Ekran Hiyerarşisi

### 5.1 Public bölüm (`/`)

```text
/
├── /                              # Landing
├── /pricing                       # Paketler ve fiyatlar (Faz 6+)
├── /how-it-works                  # Ürünün çalışma mantığı
├── /examples                      # Örnek üretim çıktıları
├── /trial                         # Ücretsiz deneme giriş noktası
├── /login
├── /register
├── /forgot-password
├── /reset-password
├── /verify-email
├── /legal
│   ├── /legal/terms
│   ├── /legal/privacy
│   ├── /legal/kvkk
│   └── /legal/scraping-policy
└── /404, /500, /maintenance
```

### 5.2 Trial / Guest deneyimi

```text
/trial
├── /trial/new                     # Anonim talep formu (rate limit'li)
├── /trial/result/{token}          # Sonuç ekranı, sınırlı kaynak
└── /trial/upgrade-cta             # Üyelik yönlendirmesi
```

### 5.3 Kullanıcı Dashboard (`/app`)

```text
/app                                # Auth gerekli
├── /app/dashboard                  # Ana özet: kalan quota, son üretimler
├── /app/generate                   # Doğal dil gündem girişi (ana akış)
│   ├── /app/generate/new
│   └── /app/generate/{requestId}/result
├── /app/generations                # Geçmiş üretimler listesi
│   ├── /app/generations/{id}
│   └── /app/generations/{id}/regenerate
├── /app/saved                      # Kaydedilen içerikler
├── /app/style-profiles             # Faz 5
│   ├── /app/style-profiles/new
│   └── /app/style-profiles/{id}
├── /app/usage                      # Quota ve kullanım grafiği
├── /app/billing                    # Faz 6
│   ├── /app/billing/plans
│   ├── /app/billing/subscription
│   └── /app/billing/invoices
├── /app/settings
│   ├── /app/settings/profile
│   ├── /app/settings/security      # password, 2FA
│   ├── /app/settings/notifications
│   └── /app/settings/api-keys      # gelecekte programatik erişim
└── /app/help
    ├── /app/help/faq
    └── /app/help/contact
```

### 5.4 Admin Panel (`/admin`)

```text
/admin                              # 2FA gerekli
├── /admin/dashboard                # KPI özet (kaynak, queue, quota)
│
├── /admin/sources                  # Faz 1 — Kaynak yönetimi
│   ├── /admin/sources                       # Liste
│   ├── /admin/sources/new                   # Yeni kaynak (RSS/Category/Manual)
│   ├── /admin/sources/{id}                  # Detay
│   ├── /admin/sources/{id}/edit
│   ├── /admin/sources/{id}/configs          # Selector versiyonları
│   ├── /admin/sources/{id}/test-listing     # Liste sayfası test ekranı
│   ├── /admin/sources/{id}/test-detail      # Detay sayfası test ekranı
│   ├── /admin/sources/{id}/health           # Source health metrikleri
│   └── /admin/sources/{id}/articles         # Bu kaynaktan gelen haberler
│
├── /admin/articles                 # Haber havuzu
│   ├── /admin/articles                      # Liste + filtre
│   ├── /admin/articles/{id}
│   ├── /admin/articles/{id}/raw             # Orijinal HTML snapshot
│   ├── /admin/articles/{id}/clean           # Temizlenmiş metin
│   ├── /admin/articles/{id}/images
│   ├── /admin/articles/{id}/reprocess       # Yeniden işleme tetikleme
│   └── /admin/articles/duplicates           # Duplicate review
│
├── /admin/media                    # Görsel arşivi
│   ├── /admin/media                         # Liste + filtre
│   ├── /admin/media/{id}                    # Görsel detay
│   ├── /admin/media/{id}/labels             # Etiketleme ekranı (Faz 4)
│   ├── /admin/media/review-queue            # Onay bekleyenler
│   └── /admin/media/duplicates
│
├── /admin/entities                 # Entity registry (Faz 4)
│   ├── /admin/entities                      # Person/Org/Location/Topic
│   ├── /admin/entities/new
│   └── /admin/entities/{id}
│
├── /admin/rag                      # Faz 2 — RAG operasyon
│   ├── /admin/rag/clusters                  # Event clusters
│   ├── /admin/rag/clusters/{id}
│   ├── /admin/rag/agenda-cards              # Gündem kartları
│   ├── /admin/rag/agenda-cards/{id}
│   ├── /admin/rag/embedding-status          # Bekleyen / başarısız
│   └── /admin/rag/search-tester             # Manuel retrieval test
│
├── /admin/generations              # Tüm kullanıcı üretimleri
│   ├── /admin/generations
│   ├── /admin/generations/{id}
│   └── /admin/generations/quality-flags
│
├── /admin/queue                    # Queue ve worker izleme
│   ├── /admin/queue/overview
│   ├── /admin/queue/jobs/{type}
│   ├── /admin/queue/failed                  # Dead letter queue
│   ├── /admin/queue/workers
│   └── /admin/queue/scheduler
│
├── /admin/users                    # Kullanıcı yönetimi
│   ├── /admin/users
│   ├── /admin/users/{id}
│   └── /admin/users/{id}/usage
│
├── /admin/plans                    # Faz 6 — Plan ve abonelik
│   ├── /admin/plans
│   ├── /admin/plans/new
│   ├── /admin/plans/{id}
│   └── /admin/subscriptions
│
├── /admin/providers                # Model & ödeme provider config
│   ├── /admin/providers/llm
│   ├── /admin/providers/embedding
│   ├── /admin/providers/rerank
│   ├── /admin/providers/vision
│   └── /admin/providers/payment
│
├── /admin/observability
│   ├── /admin/observability/metrics
│   ├── /admin/observability/logs
│   ├── /admin/observability/audit-log       # Admin action log
│   └── /admin/observability/storage         # Disk / DB / MinIO
│
└── /admin/settings
    ├── /admin/settings/system               # Quota, rate limit, feature flags
    ├── /admin/settings/security             # 2FA, RBAC
    ├── /admin/settings/backup
    └── /admin/settings/scraping-policy
```

---

## 6. Navigasyon Yapısı

### 6.1 Global navigasyon kuralları

```text
- Public: top-bar (logo, How it works, Pricing, Examples, Login, Register)
- User app: side-bar (collapsible) + top-bar (search, quota, user menu)
- Admin: side-bar (mega-grouped) + top-bar (env badge, audit shortcut, user menu)
```

### 6.2 User dashboard sidebar grupları

```text
[Çalışma]
  - Dashboard
  - Yeni İçerik Üret           (primary action)
  - Geçmiş Üretimler
  - Kaydedilenler
[Profil]
  - Stil Profilleri            (Faz 5)
  - Ayarlar
[Hesap]
  - Kullanım & Quota
  - Faturalama                 (Faz 6)
  - Yardım
```

### 6.3 Admin panel sidebar grupları

```text
[İçerik Operasyonu]
  - Dashboard
  - Kaynaklar
  - Haberler
  - Görseller
  - Entity Registry
  - RAG / Gündem Kartları
[Kullanıcı]
  - Üretimler
  - Kullanıcılar
  - Planlar & Abonelikler
[Sistem]
  - Queue & Workers
  - Provider'lar
  - Observability
  - Ayarlar
```

### 6.4 Breadcrumb prensibi

```text
Tüm /admin ve /app derinliklerinde breadcrumb zorunludur.
Örnek:
Admin > Kaynaklar > BBC Türkçe > Detay Sayfası Test
```

---

## 7. Veri Modeli Haritası (Entity İlişkileri)

### 7.1 Çekirdek varlık ilişki diyagramı

```text
users ──< sessions
users ──< subscriptions >── plans
users ──< usage_events
users ──< generations
users ──< style_profiles ──< style_samples

sources ──< source_configs (versioned)
sources ──< source_health (1:1 latest)
sources ──< articles
articles ──< article_images
articles ──< article_chunks
article_chunks >── (embedding) pgvector

articles >─┬─< event_articles >── event_clusters
event_clusters ──< agenda_cards
agenda_cards >── (embedding) pgvector

article_images ──< image_analysis (1:1)
article_images ──< image_embeddings (1:1)
article_images ──< image_labels >── entities

generations >── agenda_cards (used_agenda_card_ids)
generations >── model_providers

crawler_jobs (queue jobs ledger)
failed_jobs (dead letter)

model_providers (config)
plans, subscriptions
```

### 7.2 Entity → Faz eşlemesi

| Entity | İlk Faz | Notlar |
|---|---|---|
| `users`, `sessions` | Faz 0 | Auth temeli |
| `sources`, `source_configs`, `source_health` | Faz 1 | Admin kontrollü |
| `articles`, `article_images` | Faz 1 | Kazıma çıktısı |
| `crawler_jobs`, `failed_jobs` | Faz 1 | Queue ledger |
| `article_chunks` (+ embedding) | Faz 2 | RAG temeli |
| `event_clusters`, `event_articles` | Faz 2 | Olay gruplama |
| `agenda_cards` (+ embedding) | Faz 2 | İçerik üretim girdisi |
| `model_providers` | Faz 2 | Provider config |
| `generations`, `usage_events` | Faz 3 | Kullanıcı üretim |
| `image_analysis`, `image_embeddings`, `image_labels`, `entities` | Faz 4 | Görsel zeka |
| `style_profiles`, `style_samples` | Faz 5 | Stil klonlama |
| `plans`, `subscriptions` | Faz 6 | Ücretlendirme |

### 7.3 Önemli kısıtlar (constraints)

```text
articles.canonical_url          UNIQUE
articles.content_hash           UNIQUE (per source_id)
articles.title_hash             INDEXED
article_chunks.embedding        ivfflat / hnsw index
agenda_cards.embedding          ivfflat / hnsw index
image_embeddings.embedding      ivfflat / hnsw index
image_labels (image_id, entity_id) UNIQUE
sources.slug                    UNIQUE
subscriptions (user_id, status='active') UNIQUE
```

---

## 8. API Yüzeyi Haritası

### 8.1 API segmentleri

```text
/public/*       — Auth gerektirmeyen, rate limit'li
/auth/*         — Login, register, password reset, 2FA
/app/*          — Kullanıcı (registered) endpointleri
/admin/*        — Super admin, RBAC + 2FA gerektirir
/internal/*     — Sadece worker'lar / iç servisler (mTLS / token)
/webhooks/*     — Ödeme provider, queue eventleri
/health, /readiness, /metrics
```

### 8.2 Endpoint matrisi (özet)

| Domain | Segment | Endpoint örnekleri |
|---|---|---|
| Auth | `/auth` | `POST /auth/register`, `POST /auth/login`, `POST /auth/2fa/verify`, `POST /auth/refresh` |
| Trial | `/public` | `POST /public/trial/generate` |
| Kaynak | `/admin` | `POST /admin/sources`, `GET /admin/sources/{id}`, `POST /admin/sources/{id}/test-listing`, `POST /admin/sources/{id}/test-detail`, `POST /admin/sources/{id}/crawl-now`, `GET /admin/sources/{id}/health` |
| Haber | `/admin` | `GET /admin/articles`, `GET /admin/articles/{id}`, `POST /admin/articles/{id}/reprocess`, `GET /admin/articles/{id}/images` |
| Görsel | `/admin` | `GET /admin/images`, `POST /admin/images/{id}/analyze`, `POST /admin/images/{id}/labels`, `PATCH /admin/image-labels/{id}` |
| Entity | `/admin` | `GET /admin/entities`, `POST /admin/entities`, `PATCH /admin/entities/{id}` |
| RAG (iç) | `/internal` | `POST /internal/rag/plan`, `POST /internal/rag/retrieve`, `POST /internal/rag/generate-card`, `POST /internal/rag/generate-content` |
| Üretim (kullanıcı) | `/app` | `POST /app/generate`, `GET /app/generations`, `GET /app/generations/{id}` |
| Stil profili | `/app` | `POST /app/style-profiles`, `GET /app/style-profiles`, `POST /app/style-profiles/{id}/samples` |
| Faturalama | `/app` | `GET /app/billing/plans`, `POST /app/billing/checkout`, `GET /app/billing/subscription` |
| Webhook | `/webhooks` | `POST /webhooks/payments/{provider}` |
| Queue | `/admin` | `GET /admin/queue/overview`, `GET /admin/queue/failed`, `POST /admin/queue/jobs/{id}/retry` |
| Provider | `/admin` | `GET /admin/providers`, `PATCH /admin/providers/{id}`, `POST /admin/providers/{id}/test` |
| Observability | `/admin` | `GET /admin/observability/metrics`, `GET /admin/observability/audit-log` |

### 8.3 Sözleşme (contract) dosyaları

```text
/docs/api.md                    — REST endpoint sözleşmeleri
/docs/agents/query-planner.md   — Bölüm 9.1 PRD
/docs/agents/agenda-card.md     — Bölüm 9.2 PRD
/docs/agents/content-generator.md — Bölüm 9.3 PRD
/packages/shared-types          — TypeScript / Pydantic ortak şemalar
```

---

## 9. İçerik Türleri ve Sözlük (Taxonomy + Glossary)

### 9.1 Çıktı içerik türleri (output types)

```text
x_post              — Tek tweet
x_thread            — Numaralı thread
summary             — Gündem özeti
analysis            — Karşılaştırmalı analiz
headline            — Başlık önerisi
content_calendar    — İçerik takvimi (haftalık)
briefing            — Source-based briefing
```

### 9.2 Zaman modları (time modes)

```text
current     — Son 24–48 saat (default)
weekly      — Son 7 gün
archive     — Belirli tarih aralığı
comparison  — İki veya daha fazla dönem
```

### 9.3 Tonlar

```text
tarafsız | eleştirel | mizahi | kurumsal | aktivist | analitik | sade | sert ama kaynaklı
```

### 9.4 Status sözlüğü (state labels)

```text
articles.status         : discovered | fetched | cleaned | failed | archived
event_clusters.status   : developing | active | cooling | stale | archived
agenda_cards.status     : developing | active | cooling | stale
article_images.status   : pending | downloaded | failed | duplicate
image_labels.status     : suggested | verified | rejected | uncertain
crawler_jobs.status     : queued | running | succeeded | failed | dead
subscriptions.status    : trialing | active | past_due | canceled | expired
generations.status      : queued | running | completed | failed | insufficient_data
```

### 9.5 Glossary

```text
Source         : Admin tarafından eklenen haber kaynağı
RSS Feed       : Keşif amaçlı; tam metin için detay sayfası kazılır
Category Page  : Liste sayfasından kart bazlı keşif
Article        : Detay sayfasından kazınmış tam haber
Chunk          : Embedding için bölünmüş haber parçası
Event Cluster  : Aynı olay için farklı kaynak haberlerin kümesi
Agenda Card    : Olayın özet + key_points + content_angles karteması
Query Planner  : Doğal dil talebi → yapılandırılmış JSON plana çevirir
Retrieval Mode : current | weekly | archive | comparison
Freshness Score: Tarihsel yakınlık skoru
Reliability    : Kaynak güvenilirlik puanı (admin tarafından atanır)
Verified Label : Admin onaylı görsel etiketi
Provider       : LLM / embedding / rerank / vision / payment adapter
```

---

## 10. Kullanıcı Akışları (User Flows)

### 10.1 Admin: Yeni RSS kaynağı ekleme

```text
1. /admin/sources/new → "RSS" türü seç
2. Kaynak adı, domain, RSS URL, dil, kategori, sıklık, reliability gir
3. Sistem RSS feed'i fetch eder, item'ları gösterir
4. Admin item link / title / pubdate alanlarını eşler
5. Detay sayfası kazıma yöntemi seç:
     - readability/trafilatura (otomatik)
     - manual selectors
6. /admin/sources/{id}/test-detail → bir item ile detay test
7. Confidence score yüksekse → Aktifleştir
8. Scheduler kaynağı interval'a göre taramaya alır
```

### 10.2 Admin: Kategori sayfası kaynağı ekleme

```text
1. /admin/sources/new → "Category page" türü seç
2. Kategori URL girilir
3. Sistem HTML fetch eder, preview gösterir
4. Card / title / link / image / date selector'ları girilir
5. Pagination tipi seçilir (none | next_link | page_param | infinite_scroll)
6. /admin/sources/{id}/test-listing → ilk 10 kart preview
7. /admin/sources/{id}/test-detail → bir kart ile detay test
8. Aktifleştir
```

### 10.3 Admin: Selector test ve düzeltme

```text
1. Source health düşerse uyarı oluşur
2. Admin /admin/sources/{id}/test-listing açar
3. Hatalı selector'ları yenisiyle değiştirir
4. Yeni source_config (versioned) kaydedilir, eskisi pasifleşir
5. Tekrar test → başarılıysa aktif
```

### 10.4 Sistem: Haber pipeline (otomatik)

```text
source.fetch_rss / source.fetch_category
   ↓
article.discover (canonical URL extraction, dedup ön-kontrol)
   ↓
article.fetch_detail (HTTP/Playwright)
   ↓
article.extract (selectors → readability → fallback)
   ↓
article.clean (boilerplate, normalize, language)
   ↓
media.discover → media.download → media.hash
   ↓
article.dedupe (canonical | content_hash | title_hash)
   ↓
status: cleaned   →   chunking + embedding kuyruğuna
```

### 10.5 Sistem: RAG indeksleme

```text
article.cleaned
   ↓
chunks oluştur (200–900 token, 50–100 overlap)
   ↓
embedding kuyruğu (provider'a göre concurrency)
   ↓
pgvector insert
   ↓
event clustering tetikleyici (son 72 saat penceresi)
   ↓
agenda card generator (LLM çağrısı)
   ↓
agenda_cards (+ embedding) yazılır
```

### 10.6 Kullanıcı: İçerik üretimi (ana akış)

```text
1. /app/generate/new
2. Kullanıcı doğal dilde gündem talebini yazar
3. Parametre seç: içerik türü, zaman modu, ton, uzunluk, kaynak gösterimi
4. POST /app/generate
   a. Query Planner çağrılır → structured plan
   b. Retrieval mode resolve edilir
   c. Retrieval (semantic + freshness + reliability)
   d. Veri yeterliliği kontrolü
       - Yetersizse: warnings ile insufficient_data döner
   e. LLM content generator (agenda_cards + plan + style_profile)
   f. Kalite kontrolü (halüsinasyon kuralları)
5. /app/generate/{requestId}/result
   - Üretim, kaynak listesi, kullanılan agenda card'lar
   - Aksiyon: Kopyala, Kaydet, Yeniden üret, Stil değiştir
6. usage_events += 1
```

### 10.7 Guest: Trial akışı

```text
1. /trial/new
2. IP + browser fingerprint kontrolü
3. Sınırlı parametre (sadece current mode, kısa uzunluk)
4. Düşük tier provider'a yönlendir
5. /trial/result/{token} → çıktı + register CTA
```

### 10.8 Admin: Görsel etiketleme (Faz 4)

```text
1. /admin/media/review-queue
2. Görsel detay: VLM caption, OCR, similar verified images
3. Entity öneri (similarity tabanlı)
4. Admin onayla / reddet / şüpheli işaretle
5. image_labels kaydı (status: verified)
6. Audit log girilir
```

### 10.9 Kullanıcı: Stil profili oluşturma (Faz 5)

```text
1. /app/style-profiles/new
2. Manuel metin örnek(ler)i ya da CSV import
3. Style analyzer prompt çalıştırılır (LLM)
4. Style profile JSON çıkarılır (sentence_length, tone, patterns, avoid)
5. Kullanıcı düzenler / onaylar
6. /app/generate'de style_profile parametresi olarak seçilebilir
```

### 10.10 Kullanıcı: Faturalama (Faz 6)

```text
1. /app/billing/plans
2. Plan seç → checkout (provider abstraction)
3. Provider redirect / sheet
4. Webhook → subscription oluştur/güncelle
5. /app/billing/subscription → durum görüntüleme
6. Quota güncellenir, model routing değişir
```

---

## 11. UI Bileşen Hiyerarşisi

### 11.1 Atomic seviye (atomic design)

```text
atoms     : Button, Input, Badge, Tag, Avatar, Chip, Spinner, Toast
molecules : SearchBar, FormField, StatCard, SourceRow, JobRow,
            CitationLink, FreshnessBadge, ConfidenceMeter,
            TimeModeSelector, ToneSelector
organisms : Sidebar, Topbar, DataTable, FilterPanel, KanbanQueue,
            SelectorTester, AgendaCardPreview, GenerationResultPanel,
            ImageLabelEditor, StyleProfileEditor, ProviderConfigForm
templates : AdminListLayout, AdminDetailLayout, UserDashboardLayout,
            GenerationLayout (split: input | result)
pages     : 5. bölümdeki tüm route'lar
```

### 11.2 Önemli ortak bileşenler ve nerede kullanıldığı

| Bileşen | Kullanım yeri |
|---|---|
| `SelectorTester` | `/admin/sources/{id}/test-listing`, `/test-detail` |
| `AgendaCardPreview` | RAG ekranı, generation result ekranı |
| `CitationList` | User result, admin generation detay |
| `FreshnessBadge` | Article list, agenda card list |
| `ConfidenceMeter` | Detail extraction, image label |
| `QueueRow` | Admin queue ekranları |
| `EntityChip` | Image label, entity registry, agenda card |
| `TimeModeSelector` | User generate, retrieval test |
| `ToneSelector` | User generate, style profile |
| `ProviderBadge` | Generation detay, admin provider listesi |

### 11.3 Bildirim sistemleri

```text
- Toast: kısa anlık (success / error / info)
- In-app notifications: queue tamamlanma, source health, quota uyarısı
- E-posta: kayıt onayı, password reset, billing
- Admin alert ekranı: kritik failure, dead letter queue
```

---

## 12. Durum (State) ve Hata Mimarisi

### 12.1 İçerik üretim sonuç durumları

```text
SUCCESS              — completed, posts/summary döner
PARTIAL              — bazı dönem eksik (comparison mode)
INSUFFICIENT_DATA    — agenda card / haber sayısı kuralları sağlanamadı
RATE_LIMITED         — kullanıcı / IP / provider quotası
PROVIDER_ERROR       — primary failed, fallback denendi, son hata
TIMEOUT              — upstream timeout
UNSAFE_OUTPUT        — kalite/halüsinasyon kontrolünde yakalandı
```

### 12.2 Crawler / pipeline durumları

```text
HTTP 429              → exponential backoff + source-level cooldown
HTTP 5xx              → 3 retry
Timeout               → 2 retry
Parser error          → retry yok, admin review queue
Media download error  → 2 retry
DLQ (failed_jobs)     → admin panelden manuel retry / silme
```

### 12.3 Veri yeterliliği kuralları (özet)

```text
current mode    : ≥ 2 agenda card  veya  ≥ 3 haber
comparison mode : her dönem için ≥ 2 agenda card  veya  ≥ 3 haber
                  ve önerilen ≥ 2 farklı kaynak
archive mode    : verilen aralıkta ≥ 1 agenda card veya retrievable chunk
```

### 12.4 Halüsinasyon koruması (prompt seviyesi)

```text
- Sadece verilen agenda card / kaynaklar kullanılır.
- Tarih, kişi, kurum, olay uydurulmaz.
- Eski olay güncel sunulmaz.
- Veri yetersizse warning döndürülür, üretim yapılmaz.
- Verified olmayan etiketler kesin ifade edilmez.
```

---

## 13. Faz Bazlı Bilgi Haritası

### Faz 0 — Altyapı

```text
Sayfalar      : (ops only) /health, /readiness
Entity'ler    : users, sessions
API           : /auth/*, /health
Provider      : ModelProvider abstraction (mock veya gerçek)
```

### Faz 1 — Admin kontrollü kaynak + haber kazıma + görsel arşiv

```text
Sayfalar      : /admin/sources/*, /admin/articles/*, /admin/media/*,
                /admin/queue/*
Entity'ler    : sources, source_configs, source_health, articles,
                article_images, crawler_jobs, failed_jobs
API           : /admin/sources/*, /admin/articles/*, /admin/queue/*
Worker        : scraper, cleaner, media
Akışlar       : 10.1, 10.2, 10.3, 10.4
```

### Faz 2 — RAG, embedding, event clustering, agenda cards

```text
Sayfalar      : /admin/rag/*, /admin/providers/*
Entity'ler    : article_chunks, event_clusters, event_articles,
                agenda_cards, model_providers
API           : /internal/rag/*, /admin/providers/*
Worker        : embedding, rag (clustering + agenda generator)
Akışlar       : 10.5
```

### Faz 3 — Kullanıcı dashboard + içerik üretimi

```text
Sayfalar      : /app/* (dashboard, generate, generations, usage, settings)
Entity'ler    : generations, usage_events
API           : /app/generate, /app/generations/*
Akışlar       : 10.6, 10.7
```

### Faz 4 — Görsel zeka + admin etiketleme

```text
Sayfalar      : /admin/media/{id}/labels, /admin/entities/*,
                /admin/media/review-queue
Entity'ler    : image_analysis, image_embeddings, entities, image_labels
API           : /admin/images/*, /admin/entities/*, /admin/image-labels/*
Worker        : vision (VLM, OCR)
Akışlar       : 10.8
```

### Faz 5 — Stil profili

```text
Sayfalar      : /app/style-profiles/*
Entity'ler    : style_profiles, style_samples
API           : /app/style-profiles/*
Akışlar       : 10.9
```

### Faz 6 — Plan + ücretlendirme + ödeme

```text
Sayfalar      : /pricing, /app/billing/*, /admin/plans/*, /admin/subscriptions
Entity'ler    : plans, subscriptions
API           : /app/billing/*, /webhooks/payments/{provider}
Akışlar       : 10.10
```

---

## 14. Çapraz Referans Matrisleri

### 14.1 Sayfa ↔ Entity matrisi (örnek satırlar)

| Sayfa | Okuduğu Entity | Yazdığı Entity |
|---|---|---|
| `/admin/sources/new` | — | `sources`, `source_configs` |
| `/admin/sources/{id}/test-listing` | `sources`, `source_configs` | (sadece test, persist yok) |
| `/admin/articles/{id}` | `articles`, `article_images`, `article_chunks` | (reprocess → `crawler_jobs`) |
| `/admin/rag/agenda-cards/{id}` | `agenda_cards`, `event_clusters`, `event_articles`, `articles` | — |
| `/app/generate/new` | `agenda_cards`, `article_chunks`, `style_profiles` | `generations`, `usage_events` |
| `/admin/media/{id}/labels` | `article_images`, `image_analysis`, `image_embeddings`, `entities` | `image_labels`, audit log |
| `/app/style-profiles/{id}` | `style_profiles`, `style_samples` | `style_profiles`, `style_samples` |
| `/app/billing/checkout` | `plans` | `subscriptions` (via webhook) |

### 14.2 Endpoint ↔ Worker tetikleyici

| Endpoint | Tetiklediği job |
|---|---|
| `POST /admin/sources/{id}/crawl-now` | `source.fetch_rss` veya `source.fetch_category` |
| `POST /admin/articles/{id}/reprocess` | `article.extract`, `article.clean`, embedding |
| `POST /admin/images/{id}/analyze` | `image.embedding`, `image.vlm`, `image.ocr` |
| `POST /app/generate` | (sync) Query plan + retrieval + LLM; usage_event |
| `POST /admin/queue/jobs/{id}/retry` | İlgili job tipini yeniden enqueue |

### 14.3 Provider tipine göre kullanım

| Provider tipi | Çağıran modüller |
|---|---|
| `LLM` | Query planner, agenda card generator, content generator, style analyzer |
| `Embedding` | Article chunk embed, agenda card embed, image embed (text descriptor) |
| `Rerank` | Retrieval pipeline (opsiyonel) |
| `Vision (VLM)` | Image caption, OCR (provider sağlıyorsa) |
| `Payment` | Checkout, webhook, subscription status |

---

## 15. Bilgi Mimarisi Özeti — Tek Bakışta Nodrat

```text
ROL          → SAYFA            → DOMAIN          → ENTITY              → API           → PROVIDER
Admin        → /admin/sources   → Source Mgmt     → sources/configs     → /admin/*      → —
Admin        → /admin/articles  → Article Pipe    → articles/images     → /admin/*      → —
Admin        → /admin/rag       → RAG             → chunks/cards/clusters → /internal/* → LLM, Embedding
Admin        → /admin/media     → Visual          → images/analysis/labels → /admin/*   → Vision (VLM/OCR)
Admin        → /admin/entities  → Entity          → entities            → /admin/*      → —
Admin        → /admin/queue     → Operations      → crawler_jobs        → /admin/*      → —
Admin        → /admin/providers → Configuration   → model_providers     → /admin/*      → —
User         → /app/generate    → Generation      → generations         → /app/*        → LLM, Embedding
User         → /app/style-*     → Style Cloning   → style_profiles      → /app/*        → LLM
User         → /app/billing     → Billing         → subscriptions/plans → /app/*        → Payment
Guest        → /trial           → Trial           → (rate limited)      → /public/*     → LLM (low tier)
```

---

## 16. Yol Haritası — Bu Dokümanın Tüketicisi Olan Diğer Belgeler

```text
product/prd.md             → Ürün gereksinimleri (kanonik kaynak)
product/information-architecture.md  → BU DOKÜMAN
engineering/architecture.md         → (Sıradaki) Teknik mimari & deployment
engineering/data-model.md           → (Sıradaki) DDL + index detayları
engineering/api-contracts.md        → (Sıradaki) OpenAPI / endpoint contracts
engineering/prompt-contracts.md     → (Sıradaki) Query planner / agenda card / content generator
design/ux-wireframes.md        → (Sıradaki) Sayfa wireframe / akış görselleri
```

---

**Notlar**

- Bu IA, PRD v0.1 ile birebir uyumlu olacak şekilde yapılandırılmıştır. PRD'nin 15. bölümündeki Agent Task Group'ları (A–I) bu dokümandaki Faz haritası ile çapraz okunabilir.
- "MVP-1 ilk teknik hedef" senaryosu (PRD §16) için minimum gerekli sayfa/entity/API kümesi: `/admin/sources/*`, `/admin/articles/*`, `/admin/queue/*`, `/admin/rag/agenda-cards`, `/app/generate`, ilgili entity'ler ve provider abstraction.
- Faz dışı (out-of-scope) öğeler 5. bölümdeki sayfa hiyerarşisinde yer almaz — kasıtlı olarak dışarıda bırakılmıştır.
