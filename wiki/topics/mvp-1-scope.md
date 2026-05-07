---
type: topic
title: "MVP-1 scope — IN/OUT/LATER tam envanter"
slug: "mvp-1-scope"
category: "synthesis"
status: "live"
created: "2026-05-08"
updated: "2026-05-08"
sources:
  - "docs/strategy/risk-register.md§4"
  - "docs/strategy/risk-register.md§4.9"
  - "INDEX.md§5b"
  - "README.md§Milestone durumu"
tags: ["mvp", "scope", "envanter", "synthesis"]
aliases: ["mvp1-scope", "mvp-1-inventory"]
---

# MVP-1 scope — IN/OUT/LATER envanteri

> **TL;DR:** MVP-1'in faz × özellik kırılımıyla tam envanter. Her PRD bölümü için **IN** (build), **OUT** (yok), **LATER** (sonraki MVP) açık. Locked karar [[mvp-1-scope-lock]] — bu topic onun detay tablosu. MVP-1 ✅ delivered (production), MVP-1.1/1.2/1.3/1.4/1.5/1.6 ✅ tamamlandı (hardening sonrası genişledi).

## Bağlam

[[mvp-1-scope-lock]] kararı **özetle** "12 sayfa, 12 tablo, ~20 endpoint" der. Bu topic her PRD bölümünün kapsamını madde madde gösterir — gelecekte "MVP-1'de bu özellik var mıydı?" sorusu için tek doğruluk kaynağı.

## Faz 0 — Altyapı

| Özellik | Durum | Not |
|---|---|---|
| Docker Compose | ✅ IN | PRD F0-R2 |
| Postgres 16 + pgvector | ✅ IN | architecture.md §5.1 |
| Redis 7 | ✅ IN | broker + cache |
| MinIO (S3 API) | ✅ IN | snapshot + backup |
| Environment config | ✅ IN | PRD F0-R3, .env + sops |
| Provider abstraction | ✅ IN | PRD F0-R4 ([[provider-abstraction]]) |
| Healthcheck endpoint | ✅ IN | `/health`, `/readiness` |
| Auth + sessions | ✅ IN | basit, **2FA YOK** (R-SEC-01 LATER) |
| Multiple LLM providers | ❌ OUT | sadece [[deepseek]] |
| Rerank provider | ❌ OUT | local bge-reranker scaffold (MVP-1.5) |
| Vision provider | ❌ OUT | MVP-1.4'te eklendi (NIM Llama 4 Maverick) |
| Local LLM (vLLM) | ❌ OUT | LATER (MVP-3+) |
| Kubernetes / Swarm | ❌ OUT | LATER (yatay ölçek MRR ≥$5K) |
| Prometheus / Grafana | ❌ OUT | basit log dosyası MVP'de yeter; Faz 2+ |
| Claude Haiku 4.5 (Pro tier) | ❌ OUT | LATER (Faz 2 — Pro launch) |
| OpenRouter fallback | ❌ OUT | LATER |

## Faz 1 — Kaynak + kazıma + görsel arşiv

| Özellik | Durum | Not |
|---|---|---|
| Source ekleme | ✅ IN | RSS only, max 3 kaynak |
| RSS parser | ✅ IN | feedparser |
| Detail page extractor | ✅ IN | readability + selector |
| Article cleaning + normalization | ✅ IN | beautifulsoup + textstat |
| Duplicate detection | ✅ IN | canonical_url + content_hash |
| Crawler queue + retry | ✅ IN | [[celery-worker]] crawl_queue, c=2 |
| Failed_jobs DLQ | ✅ IN | basit, admin panelinden manuel retry |
| Source health basic | ✅ IN | beat task 6 saatte bir |
| Article images — process & discard (#304) | ✅ IN (MVP-1.4) | Bytes saklanmaz; NIM VLM caption + OCR + depicts |
| Site profile sistemi | ✅ IN (MVP-1.4) | BBC/Habertürk/Evrensel/AA/TRT/Yeşil Gazete |
| Category page kaynak | ❌ OUT | LATER MVP-2 #71 (delivered) |
| Manual URL import | ❌ OUT | LATER |
| Pagination handling | ❌ OUT | LATER MVP-2 |
| Playwright JS-render | ❌ OUT | LATER MVP-2 |
| Selector test UI tam | ❌ OUT | LATER MVP-2 #70 (delivered) |
| Source config versioning | ❌ OUT | LATER MVP-2 #75 (delivered) |
| Multi-language detection | ❌ OUT | TR varsayılan |
| Görsel bytes storage | ❌ OUT | süresiz iptal — process & discard |
| Perceptual hash, sha256 | ❌ OUT | dedup gerekli değil — URL canonical yeterli |
| HTML snapshot storage | ❌ OUT | LATER (cold tier MVP-1.5) |

## Faz 2 — RAG, embedding, agenda cards

| Özellik | Durum | Not |
|---|---|---|
| Article chunking | ✅ IN | basit, ~500 token avg |
| Embedding | ✅ IN | [[nim-bge-m3]] (1024-dim) |
| pgvector ivfflat index | ✅ IN | data-model.md |
| Semantic search | ✅ IN | basic cosine |
| Agenda card generator | ✅ IN | LLM call (DeepSeek) |
| Event clustering | ✅ IN | basic similarity threshold |
| Current mode retrieval | ✅ IN | son 24-48h |
| Weekly mode | ❌ OUT | LATER MVP-2 (query planner zaten destekliyor) |
| Archive mode | ❌ OUT | LATER MVP-2 |
| Comparison mode | ❌ OUT | LATER (R-PRD-03 telemetry — MVP-2 #51 feature flag delivered) |
| Rerank | ❌ OUT | LATER MVP-1.1 cross-encoder #181 (delivered) |
| Importance score | ❌ OUT | constant=0.5; LATER (sinyal toplaması sonra) |
| Source reliability score | ❌ OUT | LATER (admin set) |
| Advanced clustering (NER) | ❌ OUT | LATER |

## Faz 3 — Kullanıcı dashboard

| Özellik | Durum | Not |
|---|---|---|
| Login/register | ✅ IN | email + password |
| Generate akışı | ✅ IN | sadece current mode |
| Output: X post (single tweet) | ✅ IN | — |
| Generation history | ✅ IN | — |
| Save generation | ✅ IN | — |
| Basic settings (profile) | ✅ IN | — |
| Quota tracking | ✅ IN | 10/ay free, hard cap |
| Insufficient data warning | ✅ IN | RAG fail → INSUFFICIENT_DATA |
| Summary output (multi-item bullet) | ✅ IN (MVP-1.1 #173) | NotebookLM-benzeri |
| Intent classifier | ✅ IN (MVP-1.1) | multi_summary \| single_post \| thread |
| Time-aware retrieval | ✅ IN (MVP-1.1) | "son N" → importance + recency |
| X thread output | ❌ OUT | LATER MVP-2 #73 (delivered) |
| Analysis / Headline / Calendar / Briefing | ❌ OUT | LATER MVP-2 (kısmi delivered) |
| Tone selection | ❌ OUT | LATER MVP-2 #74 (delivered, 8 tone) |
| Length selection | ❌ OUT | LATER MVP-2 #74 (delivered, 3 length) |
| Source visibility toggle | ❌ OUT | her zaman göster (citation %100 hedefiyle uyumlu) |
| Regenerate button | ❌ OUT | kullanıcı yeni gen yapar |
| Style profile selection | ❌ OUT | LATER MVP-3 (Faz 5) |
| Trial (kayıtsız) flow | ❌ OUT | sadece register sonrası; **MVP-2'de KALDIRILDI** (#72 refactor) |

## Faz 4 — Görsel zeka

```text
MVP-1: YOK ❌
ANCAK: MVP-1.4'te kısmi olarak eklendi:
  ✅ NIM Llama 4 Maverick VLM (caption + OCR + depicts)
  ✅ Process & discard mimarisi
  ✅ Site profile sistemi
  ✅ suggest_image generation entegre

OUT (MVP-1.4'e kadar):
  ❌ VLM caption                    → ✅ MVP-1.4 #304
  ❌ OCR                            → ✅ MVP-1.4 #304
  ❌ Image embeddings               → MVP-3+ (eğer ihtiyaç)
  ❌ Entity registry                → MVP-3+
  ❌ Admin labeling UI              → MVP-3+
  ❌ Görsel destekli içerik         → ✅ MVP-1.4 (suggest_image)
```

## Faz 5 — Stil profili

```text
MVP-1: YOK ❌
LATER (MVP-3 hedef):
  - Pro tier hook için
  - Retention data sonra
Risk: R-PRD-04 (düşük adoption) — beta kararı
```

## Faz 6 — Ödeme

```text
MVP-1: YOK ❌
LATER (MVP-3 ZORUNLU):
  ❌ Plan management
  ❌ Subscription
  ❌ Iyzico / PayTR / Stripe
  ❌ e-Arşiv fatura
  ❌ Webhooks
  
Faz 1+2+3 stable + retention kanıtlandıktan sonra
Ödeme entegrasyonu 4-6 hafta iş
Avukat / muhasebeci eşliğinde
```

## Sapma / scope expansion (MVP-1.x'lerde)

MVP-1 production launch sonrası 6 hardening fazı (MVP-1.1, 1.2, 1.3, 1.4, 1.5, 1.6) eklendi — orijinal cut-list'i aştı. Bu **kontrolsüz scope creep değil**, kanıt-bazlı genişleme:

| Sürüm | Eklenen | Sebep | Cut-list ihlali mi? |
|---|---|---|---|
| MVP-1.1 | Eval framework, citation, RAPTOR, geographic filter, importance scoring | Halü < %2 + citation %100 hedefleri için zorunlu | Hayır (MVP-1 acceptance kriteri) |
| MVP-1.2 | Admin Settings Panel (42 setting + 3 LLM prompt runtime tunable) | Operasyonel ihtiyaç (config rebuild olmadan) | Belki — Settings UI cut-list'te yoktu |
| MVP-1.3 | UI Modernization (shadcn) | Tasarım borcu temizleme | Belki — UI revamp cut-list dışıydı |
| MVP-1.4 | Image Pipeline (VLM) | Storage cost mitigation (R-OPS-05 ✅ çözüldü) | Hayır (process & discard gerekçeli) |
| MVP-1.5 | Infra Migration ([[contabo-vps-hosting]] + Object Storage + binary quantization scaffold) | Capacity + cost optimization | Hayır (operasyonel zorunluluk) |
| MVP-1.6 | Admin observability + landing redesign | UX polish + admin operasyon | Belki — ölçek belirsiz |

> **Aksiyon:** MVP-1.x sapma analizi `nodrat-dev` ile retrospektif issue olarak açılabilir. "Cut-list disiplini sürdürülebilir mi?" sorusu için.

## İlişkiler

- **Beslediği kararlar:** [[mvp-1-scope-lock]] (bu topic'in özet halı).
- **İlgili kavramlar:** [[mvp-cut-list-method]] (metodoloji), [[kill-switch]] (KS-1 acceptance).
- **İlgili topics:** [[mvp-roadmap]] (MVP-2/3/4 timeline), [[risk-catalog]] (cut'larla ilişkili riskler).
- **İlgili varlıklar:** [[deepseek]], [[nim-bge-m3]], [[contabo-vps]], [[celery-worker]].

## Açık sorular / TODO

- **MVP-1.x scope expansion gerekçeleri:** Yukarıdaki tablo ihtiyat ile yazıldı. Her hardening için resmi gerekçe issue yok (1.2/1.3/1.6 belirsiz). Retro analizi yapılabilir.
- **OUT → LATER transition:** Bazı OUT'lar MVP-2'de LATER → IN dönüştü (selector test UI, X thread, tone). Bu transition'ın "feature gating revize" KS-1 kabul kriterinin sonucu olduğu net değil.

## Kaynaklar

- [docs/strategy/risk-register.md §4 (cut-list)](../../docs/strategy/risk-register.md)
- [docs/strategy/risk-register.md §4.9 (MVP-1 final scope)](../../docs/strategy/risk-register.md)
- [INDEX.md §5b (milestone tablosu)](../../INDEX.md)
- [README.md (Milestone durumu)](../../README.md)
- [CHANGELOG.md](../../CHANGELOG.md) — sürüm geçmişi
