# Nodrat — Risk Register & MVP Cut-List

**Doküman türü:** Risk Management & MVP Scope Decision
**Sürüm:** v0.1
**Bağımlılık:** PRD v0.1, IA v0.1, Discovery v0.1, Competitive v0.1, Unit Economics v0.1, Pricing v0.1, Legal v0.1
**Hedef:** Tüm projenin risk envanterini tek dokümanda toplamak ve PRD'deki 6 fazlı geniş kapsamı **MVP-1 minimum kabul edilebilir ürün**'e indirmek.

---

## 0. Yönetici Özeti

```text
Kapsam riski (önemli):
  PRD 6 faz × ~150 alt-gereksinim
  → Build edilirse ~10–14 ay (gerçekçi)
  → MVP-1 kapsamı 2–3 ay olmalı
  → Cut-list bu dokümanda

Top 5 risk (proje genelinde):
  R-LGL-02: Telif (FSEK)             — Skor 12 🔴
  R-PRD-01: Halüsinasyon liability    — Skor 9  🔴
  R-LGL-01: KVKK ihlali              — Skor 9  🔴
  R-OPS-01: Kaynak HTML kırılganlığı  — Skor 9  🔴
  R-FIN-01: LLM cost runaway          — Skor 9  🔴

MVP-1 kararı:
  IN:  3 RSS kaynağı, current mode, X post output, kayıtlı user
  OUT: Görsel zeka, stil profili, ödeme, 2FA admin, comparison mode

Kill-switch noktaları:
  KS-1: Faz 1 sonu — kaynak başına başarılı extraction <%70 → durdurma
  KS-2: Faz 2 sonu — agenda card kalitesi <%60 → re-design
  KS-3: Faz 3 sonu — beta retention D7 <%30 → discovery'e dön
```

---

## 1. Risk Register Metodolojisi

### 1.1 Skorlama

```text
Olasılık:  1 (çok düşük) — 2 (düşük) — 3 (orta) — 4 (yüksek) — 5 (çok yüksek)
Etki:      1 (önemsiz) — 2 (düşük) — 3 (orta) — 4 (yüksek) — 5 (kritik)
Skor:      Olasılık × Etki (1-25)

Kırmızı 🔴: 9+   (yüksek öncelik, mitigation gerek)
Sarı   🟡: 4-8  (izleme, plan)
Yeşil  🟢: 1-3  (kabul edilebilir)
```

### 1.2 Risk kategorileri

```text
LGL  : Yasal & Compliance
PRD  : Ürün riski (kalite, kullanıcı deneyimi)
TCH  : Teknik altyapı
OPS  : Operasyonel
FIN  : Finansal / cost
MKT  : Pazar / rekabet
SEC  : Güvenlik
PEO  : İnsan / takım
```

---

## 2. Risk Register (30 risk)

### 2.1 🔴 Yüksek öncelik (skor ≥9)

| ID | Risk | O | E | Skor | Tetikleyici | Mitigation |
|---|---|---|---|---|---|---|
| **R-LGL-02** | FSEK telif tazminat | 3 | 4 | 12 | Tam metin reproduction kullanıcıya | Output 25 word cap + kaynak gösterimi + ToS sorumluluk transferi |
| **R-PRD-01** | Halüsinasyon → kullanıcı tazminat | 3 | 3 | 9 | RAG dışı bilgi üretimi | PRD §12.4 prompt kuralları + insufficient_data fallback |
| **R-LGL-01** | KVKK ihlali (kullanıcı veri) | 3 | 3 | 9 | Açık rıza eksikliği | Aydınlatma metni + register flow checkbox + DPO outsource |
| **R-OPS-01** | Kaynak HTML kırılganlığı | 3 | 3 | 9 | Site redesign / yapı değişimi | Source health monitoring + selector test + admin uyarı |
| **R-FIN-01** | LLM cost runaway | 3 | 3 | 9 | Provider quota cap eksik | Per-user concurrency + provider hard cap + alarm |
| **R-MKT-01** | ChatGPT TR gündem feature | 3 | 3 | 9 | OpenAI lokalizasyon | Niş derinlik (comparison + stil) + medya partnership |
| **R-PRD-02** | Beta retention <%30 (D7) | 3 | 3 | 9 | Wrong persona, wrong UX | Discovery validation + iteration + feature gating revize |

### 2.2 🟡 Orta öncelik (skor 4-8)

| ID | Risk | O | E | Skor | Tetikleyici | Mitigation |
|---|---|---|---|---|---|---|
| **R-LGL-03** | Robots.txt ihlali → IP ban | 4 | 2 | 8 | Aşırı request | Rate limit per domain + good UA |
| **R-LGL-11** | Yurt dışı veri transfer | 4 | 2 | 8 | Provider US/HK | Açık rıza + SCC |
| **R-FIN-02** | DeepSeek API instability | 3 | 3 | 9 | Provider downtime | OpenRouter fallback + GPT-4o-mini son çare |
| **R-FIN-03** | NIM free tier kapanması | 3 | 2 | 6 | Provider policy | Local bge-m3 fallback hazır |
| **R-OPS-02** | VPS tek nokta arıza | 2 | 4 | 8 | Disk/network failure | Backup zorunlu, recovery runbook |
| **R-OPS-03** | Backup başarısızlığı | 2 | 4 | 8 | Sessiz backup hatası | Restore drill ayda 1 |
| **R-OPS-04** | Spam/bot abuse | 4 | 2 | 8 | Rate limit zayıflığı | Multi-layer rate limit + fingerprint |
| **R-TCH-01** | pgvector ölçek limiti | 3 | 2 | 6 | 1M+ chunk sonrası | ivfflat → hnsw geçiş plan |
| **R-TCH-02** | Embedding queue backlog | 3 | 2 | 6 | Provider throttle | Local fallback otomatik |
| **R-TCH-03** | Playwright kullanımı resource | 3 | 2 | 6 | JS-render gerektiren site | Sadece zorunluda kullan |
| **R-PRD-03** | Comparison mode imaginary | 3 | 2 | 6 | Kullanıcı kullanmaz | Beta usage telemetry + feature kill |
| **R-PRD-04** | Stil profili düşük adoption | 3 | 2 | 6 | Faz 5 değer üretmez | Beta sonrası karar, kesilebilir |
| **R-MKT-02** | "ChatGPT yeter" pazar tepkisi | 3 | 3 | 9 | Niş anlaşılmaz | Türkçe gündem moat vurgusu |
| **R-MKT-03** | Düşük WTP (10$ max) | 3 | 3 | 9 | Pricing yanlış | A/B test, downsize tier |
| **R-MKT-04** | Türkiye economic downturn | 3 | 2 | 6 | Makroekonomik | TL fiyat ayarlanabilir |
| **R-LGL-04** | 5651 takedown gecikmesi | 2 | 3 | 6 | İçerik yayını talep | 24h SLA prosedür |
| **R-LGL-10** | Vergi/e-Fatura uyumsuzluk | 2 | 4 | 8 | Faz 6 launch öncesi | Iyzico e-Arşiv entegrasyonu |
| **R-SEC-01** | Admin panel breach | 2 | 4 | 8 | 2FA eksikliği | 2FA zorunlu Faz 6 öncesi |
| **R-SEC-02** | Prompt injection (haber → LLM) | 3 | 2 | 6 | Kazınan içerikte instruction | System prompt isolation + sanitize |
| **R-SEC-03** | API key sızıntısı | 2 | 4 | 8 | Repo / log leak | Secret manager + git-secrets |
| **R-PEO-01** | Solo founder bandwidth | 4 | 3 | 12 | Her şeyi tek başına | MVP cut + agent kullanımı |

### 2.3 🟢 Düşük öncelik (skor ≤3)

| ID | Risk | O | E | Skor | Notlar |
|---|---|---|---|---|---|
| R-LGL-06 | Basın kanunu yanlış statü | 1 | 1 | 1 | "Üretim aracıyız" pozisyonu |
| R-LGL-07 | RTÜK kapsam | 1 | 1 | 1 | Yayın platformu değiliz |
| R-LGL-08 | X Developer Policy | 1 | 1 | 1 | MVP'de X API yok |
| R-LGL-09 | Çocuk koruması | 1 | 2 | 2 | 18+ ToS |
| R-LGL-12 | Tüketici Kanunu | 1 | 2 | 2 | 14 gün cayma yapısı |
| R-OPS-05 | Görsel storage growth | 2 | 1 | 2 | TTL policy + tiered storage |

---

## 3. En Kritik 7 Risk — Detay

### 3.1 R-LGL-02: FSEK Telif Tazminat (Skor 12)

```text
Senaryo: Bir gazete (örn. Sabah, Sözcü) Nodrat'ın haberlerini "yeniden
         yayınladığını" iddia ederek tazminat davası açar.

Olasılık (3): Türkiye'de henüz haber-RAG davası yok ama olabilir.
Etki (4):     Tazminat 50K-1M TL + reputational damage.

Mitigation matrisi:
  M1. Hard rule: Output'ta ≤25 kelime direct quote
  M2. Tüm üretimlerde kaynak link gösterimi
  M3. ToS'ta "kullanıcı sorumluluğu" net madde
  M4. Source ekleme: paywall HARAM, robots.txt uyum
  M5. Avukat ön-görüş (Faz 0)
  M6. Output kalite kontrol: alıntı tespit + flag
  M7. Gazete partnership stratejisi (Q3 2026+)

Kontrol checkpoint:
  - Faz 1 sonu: Avukat review kılavuzu uygulanıyor mu
  - Faz 3 sonu: 100 örnek output review (telif riski)
  - Aylık: Kaynak başına direct quote oranı raporu

Kabul kriteri (Risk azaldı):
  Skor 12 → 6 (Olasılık 3→2, Etki 4→3)
  Mitigation matrisi tam uygulandığında
```

### 3.2 R-PRD-01: Halüsinasyon Liability (Skor 9)

```text
Senaryo: Nodrat "X kişisi şunu söyledi" halüsinasyonu üretir.
         Kullanıcı X'te paylaşır. Tekzip + tazminat geliyor.

Olasılık (3): LLM halüsinasyonu doğal, RAG ile azalır ama sıfır değil.
Etki (3):     5237 md.125 (hakaret), tazminat 50-500K TL.

Mitigation:
  M1. PRD §12.4 prompt kuralları zorunlu
  M2. RAG dışı bilgi üretimi yasağı (system prompt)
  M3. Veri yetersizliği → INSUFFICIENT_DATA döner
  M4. Output disclaimer: "Yayınlamadan kontrol edin"
  M5. Sensitive entity list (politik figürler) ek kontrol
  M6. Kullanıcı flagging mekanizması
  M7. ToS sorumluluk transferi

Kontrol:
  Aylık: Kullanıcı flag oranı / toplam üretim
  Aylık: Hallucination test seti (golden set) skorlama
  Hedef: <%2 false positive content
```

### 3.3 R-LGL-01: KVKK İhlali (Skor 9)

```text
Senaryo: Kullanıcı verisi izinsiz işlenir. KVK Kurul incelemesi.

Olasılık (3): Aydınlatma + rıza akışı eksikse büyük olasılık.
Etki (3):     50K-2.5M TL idari para cezası.

Mitigation: §2 Legal Brief (full)
Kontrol: VERBİS gönüllü kayıt (1K+ user), DPO aylık raporu
```

### 3.4 R-OPS-01: Kaynak HTML Kırılganlığı (Skor 9)

```text
Senaryo: Sabah/Sözcü/Hürriyet site redesign yapar. Selector'lar bozulur.
         24-72 saat data akışı durur.

Olasılık (3): Yıllık 2-3 kaynak değişir (gerçekçi).
Etki (3):     Kullanıcılar fresh content göremez, churn.

Mitigation:
  M1. Source health monitor (PRD §1.10)
  M2. Selector test ekranı (PRD §1.4)
  M3. Selector versioning (rollback)
  M4. 3-tier extraction stratejisi (selectors → readability → fallback)
  M5. Admin alert sistemi
  M6. RSS-only kaynaklar daha stable (preferans)

Kontrol:
  Günlük: Source health dashboard
  Haftalık: Failed extraction trend
  Aylık: Selector yenileme prosedürü drill
```

### 3.5 R-FIN-01: LLM Cost Runaway (Skor 9)

```text
Senaryo: Bir kullanıcı script yazar, API'yi yağmalar.
         Veya bir hata loop'u her saniye LLM çağrısı yapar.
         Aylık $1.000+ unbudgeted spend.

Olasılık (3): Rate limit eksikliğinde yüksek.
Etki (3):     Margin yer, cash flow şoku.

Mitigation:
  M1. Per-user rate limit (saatlik + günlük)
  M2. Provider başına aylık hard cap
  M3. Concurrent generation limit per user
  M4. Cost-per-user alarm ($5/gün/user)
  M5. Anomaly detection (10x normal kullanım flag)
  M6. Circuit breaker pattern

Kontrol:
  Saatlik: Provider spend rate
  Günlük: Top 20 user cost report
  Anlık: Anomaly alarm Slack
```

### 3.6 R-MKT-01: ChatGPT TR Gündem (Skor 9)

```text
Senaryo: OpenAI Türkçe gündem agentı çıkarır. Anchor ayarlanmış pazar.

Olasılık (3): 12-24 ay içinde olabilir.
Etki (3):     SAM önemli ölçüde daralabilir.

Mitigation:
  M1. Niş derinlik (comparison, stil profili, görsel)
  M2. Türk medya partnership (uzun vadeli)
  M3. Brand identity creator-spesifik
  M4. Switching cost: kullanıcı stil + saved generations
  M5. Fast iteration küçük takım avantajı

Kontrol:
  Çeyreklik: Rakip feature scan
  Yıllık: Pazar payı + retention analizi
```

### 3.7 R-PEO-01: Solo Founder Bandwidth (Skor 12)

```text
Senaryo: Tek kişi tüm fazları geliştirip operasyonu yürütür.
         Burnout, kalite düşüşü, hız kaybı.

Olasılık (4): Solo founder yaygın senaryo.
Etki (3):     Proje 12-18 ay yerine 24+ aya yayılır.

Mitigation:
  M1. MVP cut-list zorunlu (bu doküman §4)
  M2. Faz 1+2 dışındakiler ertelenebilir
  M3. AI agent kullanımı (Claude Code, Cursor)
  M4. Outsource: tasarım, hukuk, content
  M5. Beta'da freelancer destek bütçesi
  M6. "Done > perfect" kuralı

Kontrol:
  Haftalık: Velocity (commit/feature)
  Aylık: Burnout self-check + holiday plan
```

---

## 4. MVP Cut-List

### 4.1 PRD'deki kapsam vs MVP-1

PRD'nin Faz 1–6'sı 6+ ay geliştirme. **MVP-1 hedefi 8–12 hafta.** Aşağıda her PRD bölümü için **IN/OUT/LATER** kararı.

### 4.2 Faz 0 — Altyapı (PRD §7 Faz 0)

```text
IN (MVP-1):
  ✅ Docker Compose (PRD F0-R2)
  ✅ Postgres + pgvector + Redis + MinIO
  ✅ Environment config (PRD F0-R3)
  ✅ Provider abstraction (PRD F0-R4) — sadece DeepSeek + bge-m3 NIM
  ✅ Healthcheck endpoint
  ✅ Auth + sessions (basit, 2FA YOK)

OUT (MVP-1):
  ❌ Multiple LLM providers (sadece DeepSeek)
  ❌ Rerank provider
  ❌ Vision provider
  ❌ Local LLM (vLLM)
  ❌ Kubernetes / Swarm
  ❌ Prometheus/Grafana — basit log dosyası MVP'de yeter

LATER (Faz 2+):
  • Claude Haiku 4.5 (Pro tier)
  • OpenRouter fallback
  • Observability stack
```

### 4.3 Faz 1 — Kaynak + kazıma + görsel arşiv

```text
IN (MVP-1):
  ✅ Source ekleme (RSS only, max 3 kaynak)
  ✅ RSS parser
  ✅ Detail page extractor (readability + selectors)
  ✅ Article cleaning + normalization
  ✅ Duplicate detection (canonical_url + content_hash)
  ✅ Crawler queue + retry
  ✅ Failed_jobs DLQ (basit)
  ✅ Source health basic
  ✅ Article images download (gallery YOK, sadece main image)

OUT (MVP-1):
  ❌ Category page kaynak (sadece RSS)
  ❌ Manual URL import
  ❌ Pagination handling
  ❌ Playwright (sadece HTTP, JS-render YOK)
  ❌ Selector test UI (admin direkt JSON girer geçici)
  ❌ Source config versioning
  ❌ Multi-language detection (TR varsayılan)
  ❌ Perceptual hash (sha256 yeterli)
  ❌ Gallery images
  ❌ HTML snapshot storage

LATER (Faz 2):
  • Category page support (5+ kaynak ihtiyacı)
  • Selector test UI tam (admin operasyonu için kritik)
  • Source config versioning
  • Pagination
  • Playwright JS-render
  • Gallery images
```

### 4.4 Faz 2 — RAG, embedding, agenda cards

```text
IN (MVP-1):
  ✅ Article chunking (basit, 500 token avg)
  ✅ Embedding (NIM bge-m3)
  ✅ pgvector ivfflat index
  ✅ Semantic search basic
  ✅ Agenda card generator (LLM call)
  ✅ Event clustering basic (similarity threshold)
  ✅ Current mode retrieval (son 24-48h)

OUT (MVP-1):
  ❌ Weekly mode
  ❌ Archive mode
  ❌ Comparison mode (imaginary feature riski R-PRD-03)
  ❌ Rerank
  ❌ Importance score (constant=0.5 set)
  ❌ Source reliability score (admin set)
  ❌ Advanced clustering (NER tabanlı)

LATER (Faz 2 sonu / MVP-2):
  • Weekly mode (kolay eklenir)
  • Comparison mode (beta usage telemetry sonra)
  • Rerank (cost-benefit analizi sonra)
  • Importance score (event signal toplaması sonra)
```

### 4.5 Faz 3 — Kullanıcı dashboard

```text
IN (MVP-1):
  ✅ Login/register (email + password, 2FA YOK)
  ✅ Generate akışı (sadece current mode)
  ✅ Output: X post (single tweet) — thread, summary, analysis YOK
  ✅ Generation history
  ✅ Save generation
  ✅ Basic settings (profile)
  ✅ Quota tracking (10/ay free, hard cap)
  ✅ Insufficient data warning

OUT (MVP-1):
  ❌ X thread output
  ❌ Summary / Analysis / Headline / Calendar / Briefing
  ❌ Tone selection (default "tarafsız")
  ❌ Length selection (default "kısa")
  ❌ Source visibility toggle (her zaman göster)
  ❌ Regenerate button (kullanıcı yeni gen yapar)
  ❌ Style profile selection
  ❌ Trial (kayıtsız) flow — sadece register sonrası

LATER:
  • Thread (popular request olursa)
  • Other output types
  • Tone variations (Faz 3 sonu)
  • Trial flow (Faz 6 launch öncesi)
```

### 4.6 Faz 4 — Görsel zeka

```text
IN (MVP-1): YOK
OUT (MVP-1):
  ❌ VLM caption
  ❌ OCR
  ❌ Image embeddings
  ❌ Entity registry
  ❌ Admin labeling UI
  ❌ Görsel destekli içerik
  
LATER (MVP-3 veya sonrası):
  Tüm Faz 4 hedefli, ürün-pazar fit kanıtlandıktan sonra
```

### 4.7 Faz 5 — Stil profili

```text
IN (MVP-1): YOK
OUT (MVP-1): Tüm Faz 5
LATER (MVP-3): Pro tier hook için, retention data sonra
Risk:  R-PRD-04 (düşük adoption) — beta kararı
```

### 4.8 Faz 6 — Ödeme

```text
IN (MVP-1): YOK
OUT (MVP-1):
  ❌ Plan management
  ❌ Subscription
  ❌ Iyzico/PayTR/Stripe
  ❌ e-Arşiv fatura
  ❌ Webhooks

LATER (MVP-3 zorunlu):
  Faz 1+2+3 stable + retention kanıtlandıktan sonra
  Ödeme entegrasyonu 4-6 hafta iş
  Avukat / muhasebeci eşliğinde
```

### 4.9 MVP-1 final scope özeti

```text
Sayfalar (12 sayfa):
  /, /login, /register, /forgot-password, /verify-email
  /app/dashboard, /app/generate/new, /app/generate/{id}/result
  /app/generations, /app/saved, /app/settings/profile
  /admin/sources, /admin/articles, /admin/queue/overview

Entity'ler (12 tablo):
  users, sessions, sources, source_configs, articles,
  article_images, article_chunks, event_clusters,
  agenda_cards, generations, usage_events, crawler_jobs

API endpoint'leri (~20):
  /auth/* (5), /admin/sources/* (4), /admin/articles/* (3),
  /admin/queue/* (2), /app/generate (1), /app/generations/* (3)
  /health, /readiness

Provider:
  LLM: DeepSeek V3 only
  Embedding: NIM bge-m3 (local fallback)

Tahmini geliştirme süresi:
  Solo founder + AI agent: 8-12 hafta full-time
  Standart takım (3 kişi): 4-6 hafta
```

---

## 5. MVP Roadmap (revize, gerçekçi)

### 5.1 MVP-1 (8-12 hafta) — "Çalışan minimum"

```text
Hafta 1-2: Faz 0 altyapı + auth
Hafta 3-5: Faz 1 (RSS only, 3 kaynak, kazıma + temizleme)
Hafta 6-7: Faz 2 (chunking + embedding + agenda card basic)
Hafta 8-9: Faz 3 (generate akışı, current mode, X post only)
Hafta 10: Internal QA + 5-10 kişi closed alpha
Hafta 11-12: Beta polish + landing page + waitlist conversion
```

### 5.2 MVP-2 (6-8 hafta sonra) — "Kullanılabilir SaaS"

```text
+ Selector test UI (admin operasyonu için kritik)
+ Category page kaynak desteği
+ Source config versioning
+ Weekly mode
+ X thread + summary output
+ Tone & length variations
+ Trial (kayıtsız) flow
+ Better quota UI
+ Beta'ya 30 davet
```

### 5.3 MVP-3 (8-10 hafta sonra) — "Ücretli launch"

```text
+ Faz 6 ödeme entegrasyonu (Iyzico TL)
+ e-Arşiv fatura
+ Plan / subscription tabloları
+ Stil profili (Faz 5 başlangıç)
+ Retention için minimum gerekli polish
+ Public launch
```

### 5.4 MVP-4+ (sonra) — "Genişleme"

```text
+ Comparison mode
+ Görsel zeka (Faz 4)
+ Stil profili tam (Faz 5)
+ Premium model tier
+ Stripe USD
+ Çoklu dil (EN)
```

---

## 6. Kill-Switch Noktaları

### 6.1 Faz/MVP geçişlerinde go/no-go

⚠️ **Research status update (2026-05-01):** 27 görüşme + prototip + pricing test tamamlandı. Çekirdek hipotezler doğrulandı (Discovery §1.3 + research-findings-integration). KS-1 acceptance for "user feedback olumlu" kanıtı güçlü; teknik kriterlere odak.

```text
KS-1: MVP-1 sonu (Hafta 12)
  Kabul kriterleri:
    [ ] 3 kaynak başarılı extraction ≥ %70 (R-OPS-01 mitigation)
    [✅] Discovery validation kanıtı (27 görüşme tamamlandı)
    [ ] Closed alpha 5+ kişi olumlu feedback
    [ ] LLM maliyeti tahmini margin uyumlu (< $0.01/gen)
    [ ] Halüsinasyon test seti < %5 false positive
    [✅] Avukat ToS/Privacy review yapılmış (legal-opinion-integration)
  
  No-go kriterleri:
    - Extraction <%50 → kazıma altyapısı yeniden
    - User feedback "ChatGPT yetiyor" → discovery'e geri
    - Maliyet >$0.05/gen → provider strateji yeniden

KS-2: MVP-2 sonu (Hafta 20)
  Kabul kriterleri:
    [ ] Beta retention D7 ≥ %30
    [ ] Beta NPS ≥ 30
    [ ] 25 persona görüşmesi tamamlandı
    [ ] Selector test UI admin tarafından kullanılıyor
    [ ] 5+ kaynak aktif

  No-go kriterleri:
    - D7 retention <%20 → ürün/persona uyumu yok, pivot
    - NPS <10 → kalite problemi
    - <5 kaynak çalışıyor → yapay zeka altyapı re-think

KS-3: MVP-3 sonu (Hafta 28)
  Kabul kriterleri:
    [ ] Free → paid conversion ≥ %3
    [ ] Trial → free conversion ≥ %20
    [ ] Pro tier en az 5 paid user (mock onboarding)
    [ ] Cost per user < tier maliyet limiti

  No-go kriterleri:
    - Conversion <%1 → pricing model yeniden
    - WTP <250 TL → tier/feature mix yeniden
```

### 6.2 Genel kill-switch

```text
- 6 ay içinde 50+ paid user yoksa → ürün-pazar fit yok, B2B pivot değerlendir
- 12 ay içinde MRR < cost (sustained) → kapatma değerlendir
- Yasal ihlal (KVKK Kurul kararı) → uyum sağlanmazsa kapatma
- Cyber breach (kullanıcı verisi sızıntı) → 30 gün uyum + bildirim
```

---

## 7. Risk Mitigation Bütçesi (önerilen)

```text
Avukat ön-görüş (Faz 0)               : 50.000 TL
DPO outsource (yıllık)                 : 30.000 TL
Cyber sigorta (Faz 6)                  : 20.000 TL/yıl (opsiyonel)
Backup off-server                      :     500 TL/ay
Provider quota cap (cost runaway):     :       0 TL (sistem)
Selector test UI (acil dev)            :       0 TL (geliştirici zamanı)
Halüsinasyon test seti hazırlama       :   5.000 TL (data labelling)
Marketing emergency (rakip launch yanıtı): 20.000 TL (hazır budget)
─────────────────────────────────────────────────────
Toplam Yıl 1 risk yatırımı            : ~125.000 TL
```

---

## 8. Karar Noktaları

| ID | Karar | Önerim | Etki |
|---|---|---|---|
| D1 | MVP-1 kapsam onayı | Bu doc §4.9 | Roadmap |
| D2 | Solo founder vs takım | İlk MVP-1 solo + agent, MVP-2'de freelance | Bütçe |
| D3 | Beta kullanıcı sayısı | Alpha 5-10, beta 30, soft launch 100 | GTM |
| D4 | Avukat zaman | Faz 0'da (kod öncesi) | Tasarım |
| D5 | Comparison mode kararı | Beta usage data sonra | MVP-2/3 |
| D6 | Görsel zeka (Faz 4) | MVP-3 sonra | Kapsam |
| D7 | Stil profili | MVP-3'te dene | Retention |
| D8 | Multi-language | TR-only başla | Kapsam |
| D9 | 2FA admin | Faz 6 öncesi | Güvenlik |
| D10 | İlk public launch tarihi | Hafta 28 hedef | Ticari |

---

## 9. Çapraz Referans

```text
R-LGL-02 (FSEK)            → Legal Brief §3
R-PRD-01 (halüsinasyon)    → PRD §12.4 + Legal §6
R-LGL-01 (KVKK)            → Legal Brief §2
R-OPS-01 (HTML kırılganlık)→ PRD §1.10 source health
R-FIN-01 (cost runaway)    → Unit Economics §6
R-MKT-01 (ChatGPT TR)      → Competitive §6.1
R-MKT-02 ("ChatGPT yeter") → Competitive §5
R-PRD-03 (comparison kill) → MVP Cut-list §4.4
R-PRD-04 (stil profili)    → MVP Cut-list §4.7
KS-1 acceptance            → Success Metrics: pilot KPI
KS-3 conversion            → Success Metrics: north star
MVP-1 scope                → IA §13 Faz haritası ile uyumlu
```

---

**Sonuç:** Top-7 kırmızı risk için **mitigation hazır**, çoğu PRD'de zaten geçiyor; eksik olan **avukat ön-görüş + DPO outsource + cost runaway alarmları** Faz 0'da çözülmeli. **MVP-1 kapsamı 12 hafta** ile gerçekçi; PRD'nin 6 fazı **MVP-1/2/3** olarak parçalanır. **Kill-switch noktaları** her MVP geçişinde uygulanmalı — özellikle KS-2 (D7 retention) **ürün-pazar fit acid testi**.
