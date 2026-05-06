# Nodrat — Doküman İndeksi

**Sürüm:** v1.3
**Son güncelleme:** 2026-05-06
**Toplam doküman:** 26+ (Faz 0-3 + alpha planning + alarm thresholds + sops + image VLM)
**MVP-1 durumu:** ✅ %100 (production'da, https://nodrat.com)
**MVP-1.1 / 1.2 / 1.3 / 1.4 durumu:** ✅ tamamlandı (production)
**MVP-1.5 durumu:** ✅ delivered 2026-05-06 (Epic #215 — Contabo VPS 40 NVMe + Object Storage migration, cold tier #219, body_html drop #220, binary quantization scaffold #221, local bge-m3 scaffold #223, local bge-reranker scaffold #224)

Bu dosya **kök dizinde tek başına** durur ve tüm projenin **navigasyon hub'ıdır**. Her doküman için: ne içerir, ne zaman bakılır, hangi diğer dokümana bağlıdır.

---

## 0. Hızlı başlangıç — sık sorulan sorular

| Soru | Bakılacak doküman |
|---|---|
| "Ürün ne yapıyor, hangi gereksinimleri var?" | [docs/product/prd.md](docs/product/prd.md) |
| "Sayfa hiyerarşisi, route'lar, entity ilişkileri?" | [docs/product/information-architecture.md](docs/product/information-architecture.md) |
| "Kim için yapıyoruz, persona doğrulandı mı?" | [docs/strategy/discovery-validation.md](docs/strategy/discovery-validation.md) + [docs/validation/research-findings.md](docs/validation/research-findings.md) |
| "ChatGPT'den farkımız ne?" | [docs/strategy/competitive-analysis.md](docs/strategy/competitive-analysis.md) |
| "Bir kullanıcı bize ayda kaça mal oluyor?" | [docs/strategy/unit-economics.md](docs/strategy/unit-economics.md) |
| "Hangi tier ne kadar, neden?" | [docs/strategy/pricing-strategy.md](docs/strategy/pricing-strategy.md) |
| "MVP'de ne var, ne yok?" | [docs/strategy/risk-register.md](docs/strategy/risk-register.md) §4 |
| "Neyi ölçüyoruz, North Star ne?" | [docs/strategy/success-metrics.md](docs/strategy/success-metrics.md) |
| "Stack ne, deployment nasıl?" | [docs/engineering/architecture.md](docs/engineering/architecture.md) |
| "Hangi tablolar, hangi alanlar, hangi indeksler?" | [docs/engineering/data-model.md](docs/engineering/data-model.md) |
| "Hangi API endpoint var, request/response nedir?" | [docs/engineering/api-contracts.md](docs/engineering/api-contracts.md) |
| "LLM prompt'ları ne, halüsinasyon nasıl önleniyor?" | [docs/engineering/prompt-contracts.md](docs/engineering/prompt-contracts.md) |
| "Saldırı yüzeyi ne, KVKK uyum nasıl?" | [docs/engineering/threat-model.md](docs/engineering/threat-model.md) |
| "Ekran nasıl görünecek, akış ne?" | [docs/design/ux-wireframes.md](docs/design/ux-wireframes.md) |
| "Marka rengi, font, copy tonu?" | [docs/design/design-system.md](docs/design/design-system.md) |
| "Yasal riskler, KVKK, FSEK, scraping ne diyor?" | [docs/legal/compliance-brief.md](docs/legal/compliance-brief.md) |
| "Avukat ne dedi, hangi noktalar lock?" | [docs/legal/opinion-integration.md](docs/legal/opinion-integration.md) |
| "27 görüşme ne çıkardı?" | [docs/validation/research-findings.md](docs/validation/research-findings.md) |
| "Kullanıcı ToS / Privacy / KVKK metinleri?" | docs/legal/tos.md, privacy-policy.md, kvkk-aydinlatma.md |
| "Veri envanteri (ROPA), DPO sözleşmesi, ihlal prosedürü?" | docs/legal/ropa.md, dpo-contract-template.md, incident-response.md |

---

## 1. Klasör yapısı

```
/Users/selmanay/Desktop/nodrat/
├── INDEX.md                                   ← bu dosya
└── docs/
    ├── product/                               # Kanonik ürün gereksinimleri
    │   ├── prd.md                             # PRD (kök kaynak)
    │   └── information-architecture.md        # IA — sayfa/entity/API haritası
    │
    ├── strategy/                              # Strateji + risk + metrik
    │   ├── discovery-validation.md            # Persona, JTBD, validation
    │   ├── competitive-analysis.md            # Rakipler + pozisyon
    │   ├── pricing-strategy.md                # Tier yapısı + funnel
    │   ├── unit-economics.md                  # Maliyet + margin
    │   ├── success-metrics.md                 # WSGAU + KPI ağacı
    │   └── risk-register.md                   # 30 risk + MVP cut-list
    │
    ├── engineering/                           # Teknik referans
    │   ├── architecture.md                    # Stack + deploy + workers
    │   ├── data-model.md                      # DDL + indekler + seed
    │   ├── api-contracts.md                   # ~50 endpoint OpenAPI
    │   ├── prompt-contracts.md                # 3 LLM prompt + eval
    │   └── threat-model.md                    # STRIDE + OWASP + AI
    │
    ├── design/                                # UX + marka
    │   ├── ux-wireframes.md                   # 8 ekran + journey map
    │   └── design-system.md                   # Renk + tipo + copy
    │
    ├── legal/                                 # Hukuki + uyum
    │   ├── compliance-brief.md                # KVKK + FSEK + 5651 risk
    │   ├── opinion-integration.md             # Avukat ön-görüşü deltaları
    │   ├── tos.md                             # Hizmet Koşulları (Faz 1)
    │   ├── privacy-policy.md                  # Gizlilik Politikası (Faz 1)
    │   ├── kvkk-aydinlatma.md                 # KVKK Aydınlatma Metni
    │   ├── cookies-policy.md                  # Çerez Politikası
    │   ├── scraping-policy.md                 # Kaynak kullanım politikası
    │   ├── dpo-contract-template.md           # DPO/KVKK uzmanı sözleşme
    │   ├── ropa.md                            # Veri İşleme Envanteri
    │   └── incident-response.md               # 72h KVKK ihlal playbook
    │
    └── validation/                            # Araştırma + kanıt
        └── research-findings.md               # 27 görüşme + prototip + WTP
```

---

## 2. Ne zaman hangi belgeye bakmalı?

### 2.1 Yeni feature geliştireceksen

```text
1. PRD — gereksinim açık mı? bağlam ne?
2. IA — bu feature hangi sayfaya / entity'ye düşer?
3. Discovery + Research — kullanıcı bunu istiyor mu?
4. Risk Register §4 — bu feature MVP-1/2/3'te mi?
5. Pricing — hangi tier'da kilit, paywall var mı?
6. UX Wireframes — ekran tasarımı + akış
7. API Contracts — endpoint + request/response
8. Data Model — tablo + alan + index
9. Architecture — worker + queue + provider
10. Prompt Contracts — LLM çağrısı varsa
11. Threat Model — güvenlik + KVKK
12. Design System — copy + ton
13. Legal/* — kullanıcı sözleşmesi etkilenir mi?
```

### 2.2 Bug yakaladığında

```text
1. Architecture — sorun hangi katmanda?
2. Data Model — schema constraint mi?
3. Prompt Contracts — eval test'e düştü mü?
4. Threat Model — güvenlik ihlali mi?
5. Risk Register — alarm eşiği aşıldı mı?
```

### 2.3 Pricing değiştireceksen

```text
1. Unit Economics — yeni margin hesabı
2. Pricing Strategy — tier mapping
3. Discovery + Research — WTP onaylı mı?
4. Data Model plans tablosu — seed güncelle
5. API Contracts — billing endpoint güncelle
6. Design System — copy guideline
```

### 2.4 Yeni kaynak ekleyeceksen (admin)

```text
1. Legal compliance §4 — robots.txt + ToS check
2. Scraping Policy — public-only kuralı
3. UX Wireframes §8 — admin ekleme akışı
4. API Contracts §4 — endpoint
5. Data Model sources tablosu
6. Risk Register R-OPS-01 — selector kırılganlığı
```

### 2.5 Veri ihlali / KVKK incident

```text
1. Incident Response (legal/incident-response.md) — 72h playbook
2. Threat Model §6 — SEV-1 prosedürü
3. Compliance Brief §2 — KVKK yükümlülük
4. ROPA — etkilenen aktivite hangisi?
5. DPO çağrı (DPO Contract template'teki iletişim)
```

### 2.6 Pre-launch checklist (Faz 0/1/6)

```text
Faz 0:
  - Compliance Brief §10.1 (avukat ön-görüş ✓ tamamlandı)
  - Opinion Integration §8 (Faz 0 sonu checklist)
  
Faz 1:
  - Opinion Integration §9 (Faz 1 launch checklist)
  - 4 takedown endpoint canlı (api-contracts §22)
  - PII redaction modülü aktif (prompt-contracts §1.5)
  - /legal/* sayfaları yayında
  - Cookie banner + register 4 checkbox
  - Source admin 5-item checklist
  
Faz 6 (paid launch):
  - Opinion Integration §10
  - Refund policy + e-Arşiv
  - 2FA admin için zorunlu
  - VERBİS değerlendirmesi
```

---

## 3. Doküman bağımlılık zinciri

```text
PRD (kök kaynak)
  ↓
Information Architecture
  ↓
  ├── Discovery → Research Findings (validation)
  │
  ├── Competitive ──┐
  ├── Unit Economics ┤
  ├── Pricing ──────┼──→ Risk Register → MVP Cut-list
  ├── Metrics ──────┘
  │
  ├── Architecture
  ├── Data Model
  ├── API Contracts
  ├── Prompt Contracts ──→ LLM Eval Framework
  ├── Threat Model
  │
  ├── UX Wireframes
  └── Design System
  
Cross-cutting:
  Legal Compliance → Opinion Integration → ToS / Privacy / KVKK / ROPA / DPO
```

**Kural:** Bir dokümanı güncellersen bağımlı olanlara da bak.

---

## 4. Çekirdek kararlar — locked

Tüm dokümanlarda tutarlı kalan kararlar:

```text
✅ Pozisyon:        "Editör odaklı üretim aracı"
✅ ChatGPT ilişki:  "Yanında, gündem için özel araç" (yerine değil)
✅ Marka:           "Nodrat haber kaynağı değildir"
✅ Birincil persona: P1A (politik creator)
✅ İkincil persona:  P1B (ajans, multi-seat MUST)
✅ Stack:           Next.js + FastAPI + Postgres+pgvector + Redis + MinIO + Caddy
✅ Default LLM:     DeepSeek V3 ($0.27/$1.10 per 1M)
✅ Premium LLM:     Claude Haiku 4.5 (Pro+ tier)
✅ Embedding:       NIM bge-m3 (free) + local fallback
✅ Auth:            JWT 15dk + refresh 30g, Argon2id
✅ North Star:      WSGAU (Weekly Saved Generations / Active User)
✅ Pricing tier:    Trial / Free / 249 / 749 / 2499 TL
✅ Margin hedef:    ≥%75 paid tier
✅ MVP-1 scope:     3 RSS, current mode, X post, 8-12 hafta
✅ Yaş gate:        18+ (16+ değil)
✅ Tam metin:       Internal RAG'de, kullanıcıya gösterme
✅ Direct quote:    25 kelime hard cap
✅ Robots.txt:      Sıfır tolerans, admin override yok
✅ Paywall:         Hard ban
✅ User-Agent:      NodratBot/1.0 (+https://nodrat.com/bot; contact: legal@nodrat.com)
✅ PII redaction:   LLM çağrısı öncesi şart (avukat eklemesi)
✅ Takedown:        4 endpoint + 24h SLA
✅ Backup:          Contabo Object Storage (S3-comp) encrypted, restore drill aylık (MVP-1.5'ten itibaren; öncesinde Backblaze B2)
✅ Hosting:         Contabo Cloud VPS 40 (12 vCPU / 48 GB / 250 GB NVMe, 20€/ay 12-ay) — dedicated MVP-1.5'ten itibaren
✅ KVKK:            Açık rıza + DPA + soft delete + 30g hard delete
```

---

## 5. Sürüm tablosu

| Doküman | Sürüm | Son güncelleme | Önemli notlar |
|---|---|---|---|
| PRD | v0.1 | 2026-05-01 | Kök kaynak, değişmedi |
| Information Architecture | v0.1 | 2026-05-01 | §1.1 pozisyon güncel |
| Discovery & Validation | v0.1 | 2026-05-01 | Validation status ✅, hipotez tablosu |
| Competitive Analysis | v0.1 | 2026-05-01 | "Editör odaklı" pozisyon, ChatGPT yanında |
| Unit Economics | v0.1 | 2026-05-01 | DeepSeek default, Haiku premium |
| Pricing Strategy | v0.1 | 2026-05-01 | Pro mesajı, Agency multi-seat MUST |
| Success Metrics | v0.1 | 2026-05-01 | B5 aha moment ✅ confirmed |
| Risk Register | v0.1 | 2026-05-01 | KS-1 acceptance status |
| Architecture | v0.1 | 2026-05-01 | — |
| Data Model | v0.1 | 2026-05-01 | — |
| API Contracts | v0.1 | 2026-05-01 | — |
| Prompt Contracts | v0.1 | 2026-05-01 | — |
| Threat Model | v0.1 | 2026-05-01 | — |
| UX Wireframes | v0.1 | 2026-05-01 | Onboarding örnek prompt strategy |
| Design System | v0.1 | 2026-05-01 | "Editör odaklı" voice |
| Legal Compliance Brief | v0.1 | 2026-05-01 | — |
| Legal Opinion Integration | v0.1 | 2026-05-01 | Avukat ön-görüş entegrasyonu |
| Research Findings | v0.1 | 2026-05-01 | 27 katılımcı araştırma |
| ToS | v0.1 | 2026-05-01 | Avukat final review bekliyor |
| Privacy Policy | v0.1 | 2026-05-01 | Avukat final review bekliyor |
| KVKK Aydınlatma | v0.1 | 2026-05-01 | Avukat final review bekliyor |
| Cookies Policy | v0.1 | 2026-05-01 | — |
| Scraping Policy | v0.1 | 2026-05-01 | — |
| DPO Contract Template | v0.1 | 2026-05-01 | KVKK uzman seçimi için |
| ROPA | v0.1 | 2026-05-01 | DPO ile birlikte güncellenecek |
| Incident Response | v0.1 | 2026-05-01 | 72h KVKK playbook |

---

## 5b. Milestone takvimi

| Milestone | Tarih hedef | Durum | İçerik |
|---|---|---|---|
| MVP-1 — Çalışan minimum (Faz 0+1+2+3) | 2026-07-31 | ✅ %100 (production'da) | RSS crawl, agenda, X post |
| **MVP-1.1 — Production Hardening** | 2026-05-15 | ✅ tamamlandı | Eval framework, citation, reranker, RAPTOR, geographic filter, importance scoring |
| **MVP-1.2 — Admin Settings Panel** | 2026-05-31 | ✅ tamamlandı (Epic #262) | 42 setting (10 grup) + 3 LLM prompt runtime tunable. SettingsStore + PromptsStore + Redis pub/sub. |
| **MVP-1.3 — UI Modernization (shadcn)** | 2026-06-07 | ✅ tamamlandı (Epic #275) | Admin paneli shadcn radix-luma preset + Sidebar primitive. Auth + legal + app layout senkron. |
| **MVP-1.4 — Image Pipeline (VLM)** | 2026-05-06 | ✅ tamamlandı (Epic #300) | Process & discard mimarisi: NIM Llama 4 Maverick VLM ile caption + OCR + depicts. Storage 5TB/yıl → 90GB/yıl (%98 azalma). Site profile sistemi (BBC/Habertürk/Evrensel/AA/TRT/Yeşil Gazete). Reklam/logo/öneri haber filter. Suggest_image generation entegrasyonu. |
| **MVP-1.5 — Infrastructure Migration** | **2026-06-15** | 📋 planlandı (Epic #215) | Contabo Cloud VPS 40 dedicated (12 vCPU / 48 GB / 250 GB NVMe), Object Storage geçişi, cold-tier retention, body_html drop, pgvector quantization, chunk dedup, local bge-m3 + bge-reranker-v2-m3 primary |
| MVP-2 — Kullanılabilir SaaS | 2026-09-29 | ⏳ planlandı | 25+ kaynak, trial flow, source versioning UI, archive mode, search-as-a-service (Epic #261), suggest_image UI hardening |
| MVP-3 — Paid Launch | 2026-11-30 | ⏳ planlandı | Billing, multi-seat, premium tier (Claude Haiku) |

---

## 6. Açık iş kalemleri (TODO)

### 6.1 Faz 0 (kod öncesi)
- [ ] DPO/KVKK uzmanı sözleşmesi (template hazır → uzman seçimi + imza)
- [ ] ROPA finalize (DPO yardımıyla, ilk taslak hazır)
- [ ] ToS/Privacy/KVKK avukat final review
- [ ] Provider DPA listesi (DeepSeek, Anthropic için)
- [ ] Domain DNS setup ✅ (yapıldı, nodrat.com Cloudflare → VPS)

### 6.2 Faz 1 (pre-public launch)
- [ ] /legal/* sayfaları canlı (8 yasal doküman web'de)
- [ ] Cookie banner aktif
- [ ] Register 4 checkbox akışı
- [ ] PII redaction modülü
- [ ] 4 takedown endpoint canlı (`/legal/abuse`, `/takedown`, `/copyright`, `/privacy-request`)
- [ ] Robots.txt parser zorunlu source ekleme
- [ ] Source admin 5-item checklist UI

### 6.3 Validation (paralel)
- [ ] V5 closed alpha (5-10 kişi)
- [ ] V6 closed beta (30 kişi) — D7/D30 retention
- [ ] V7 PMF survey (Sean Ellis, %40 hedefi)

---

## 7. Konvansiyonlar

```text
- Tüm dokümanlar Markdown (.md)
- Türkçe primary, gerekirse İngilizce kavramlar
- Versiyon: v0.X (frontmatter'da)
- Tarih: ISO 8601 (2026-05-01)
- Para: TL primary, USD secondary
- Section numarası: §1.2.3 formatında
- Cross-reference: "Discovery §3.6" → docs/strategy/discovery-validation.md §3.6
- Frontmatter zorunlu: doküman türü, sürüm, bağımlılık, hedef
```

---

## 8. Birinci ve ikinci derece bağımlılıklar — özet

```text
Kanonik kaynak:        product/prd.md
Birinci derece:        product/information-architecture.md
İkinci derece (P0):    strategy/* (6 doküman)
İkinci derece (P1):    engineering/* (5 doküman) + design/* (2 doküman)
Cross-cutting:         legal/* (10 doküman)
Validation:            validation/research-findings.md

Integration docs (delta map):
  legal/opinion-integration.md     — avukat ön-görüş entegrasyonu
  validation/research-findings.md  — 27 görüşme entegrasyonu
```

---

**Sonuç:** Bu indeks tek başına root'ta durur. Tüm diğer dokümanlar `docs/` altında kategorize edildi. Yeni bir konuya başlarken yukarıdaki "sık sorulan sorular" tablosundan başla. Cross-reference için "doküman adı + section" konvansiyonunu koru.
