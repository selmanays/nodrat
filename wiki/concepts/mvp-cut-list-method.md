---
type: concept
title: "MVP cut-list (IN/OUT/LATER) framework"
slug: "mvp-cut-list-method"
category: "framework"
status: "live"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/strategy/risk-register.md§4"
  - "docs/strategy/risk-register.md§4.9"
tags: ["mvp", "scope", "method", "framework"]
aliases: ["cut-list", "in-out-later", "scope-cut"]
---

# MVP cut-list framework

> **TL;DR:** Nodrat'ın PRD'deki 6 fazlı geniş kapsamından MVP-1 minimum kabul edilebilir ürüne inmek için kullanılan disiplin: her özellik için **IN / OUT / LATER** kararı. Cut-list scope creep'e karşı bekçi; solo founder + AI agent kombinasyonunun sürdürülebilir olmasını sağlayan disiplin.

## Tanım

Klasik "MVP scope reduction" pattern'i. Her PRD bölümü/feature için 3 kategoriden birine atılır:

- **IN** — MVP-1 build edilir.
- **OUT** — MVP-1'de yok, ileride değerlendirilebilir.
- **LATER** — MVP-2 veya MVP-3'te eklenmesi planlı (timeline ile).

Yapı:

1. PRD'nin tüm faz/bölümlerini tara (Faz 0-6).
2. Her bölüm için IN/OUT/LATER kararı al.
3. IN listesi → MVP-1 final scope.
4. LATER listesi → MVP-2/3 backlog.
5. OUT listesi → backlog (deferred indefinitely).

## Neden Nodrat'ta var

Üç motivasyon:

1. **R-PEO-01 (solo founder bandwidth, skor 12).** PRD'nin 6 fazı tam build edilse 10-14 ay; solo founder + AI agent için sustainable değil. Burnout riski.
2. **Time-to-market.** Pricing-strategy.md ve discovery-validation.md "8-12 hafta MVP" hedefliyor; cut-list bu zaman bütçesini zorlamak için.
3. **Kanıt-bazlı feature kararı.** Comparison mode (R-PRD-03), stil profili (R-PRD-04) gibi "imaginary feature" riskleri var. Cut-list bu özellikleri **beta usage telemetry sonrasına** erteleyerek validation'sız build'e karşı koruma.

## Decision framework

Her PRD bölümü için sorulan sorular:

```text
Q1. Bu özellik PRD'de mi?           → Evet (zaten kapsamda)
Q2. Bu özelliği ihmal edersek...
    a) ürün çalışır mı?              → Evet → muhtemel OUT/LATER
    b) ürün-pazar fit kanıtlanabilir mi? → Evet → muhtemel LATER
    c) müşteri başlamak için ister mi?   → Hayır → muhtemel OUT
Q3. Build maliyeti?
    <1 hafta                          → IN düşünülebilir
    1-4 hafta                         → LATER (eğer çekirdek değilse)
    >4 hafta                          → OUT (eğer çekirdek değilse)
Q4. Bağımlılık zinciri?              → Bağımlı feature'lar IN'se bu da IN
Q5. Risk-register'da mı?              → "Imaginary feature" riski varsa LATER
```

## Faz × kategori örnekleri (risk-register §4)

| Faz | IN örneği | OUT örneği | LATER örneği |
|---|---|---|---|
| **Faz 0** | Docker Compose, Postgres+pgvector, basit auth | Multiple LLM, k8s, Prometheus | Anthropic Pro tier, OpenRouter fallback |
| **Faz 1** | RSS only, 3 kaynak | Category page, Playwright, görsel bytes | Selector test UI tam, pagination |
| **Faz 2** | Embedding, agenda card, current mode | Comparison mode, rerank, importance | Weekly mode, comparison (telemetry sonrası) |
| **Faz 3** | Login, X post, history, save | Tone variations, regenerate, trial flow | Thread, analysis output |
| **Faz 4** | YOK | Tüm görsel zeka | MVP-3+ kararı |
| **Faz 5** | YOK | Tüm stil profili | MVP-3'te dene |
| **Faz 6** | YOK | Lemon Squeezy MoR (Iyzico/e-Arşiv reddedildi — [[lemon-squeezy-payment-provider]]) | MVP-3 zorunlu |

## MVP-1 final scope çıktısı (§4.9)

Cut-list'in nihai sonucu:

```text
Sayfalar:        12
Tablolar:        12
API endpoint'ler: ~20
Provider:         DeepSeek + bge-m3 NIM only
Tahmini süre:     8-12 hafta solo + agent
```

Detay: [[mvp-1-scope-lock]] (locked decision olarak), [[mvp-1-scope]] (topic — tam IN/OUT envanteri).

## Risk-bazlı kesim örnekleri

Cut-list bazı feature'ları doğrudan risk-register'dan tetiklenen kararla erteler:

| Feature | Risk | Cut sonucu | Sebep |
|---|---|---|---|
| Comparison mode | R-PRD-03 (imaginary feature) | LATER (MVP-2 telemetry sonra) | Beta usage data olmadan build = boş emek |
| Stil profili (Faz 5) | R-PRD-04 (düşük adoption) | LATER (MVP-3) | Pro tier hook için, retention kanıtı sonra |
| Görsel zeka tam (Faz 4) | — | MVP-3+ veya iptal | Faz 1-3 stable + ürün-pazar fit sonra |
| Multi-language | — | MVP-4+ | TR primary, EN sonra |
| 2FA admin | R-SEC-01 | LATER (MVP-3 öncesi) | Faz 6 launch öncesi şart |

## İlişkiler

- **İlgili kavramlar:** [[risk-scoring]] (cut kararlarını besler), [[kill-switch]] (MVP geçişlerinde feature gating revize).
- **İlgili kararlar:** [[mvp-1-scope-lock]] (cut-list'in somut çıktısı).
- **İlgili topics:** [[mvp-1-scope]] (envanter), [[mvp-roadmap]] (timeline).
- **İlgili varlıklar:** —

## Açık sorular / TODO

- **Cut decision audit:** MVP-1.1/1.2/1.3/1.4'te scope expansion oldu mu (12 sayfa → 12+ , 12 tablo → 12+)? Bu "controlled expansion" mı yoksa scope creep mi?
- **MVP-2 cut-list detay:** §5.2'de 12 issue + 17 PR delivered. Ama "OUT/LATER" kategori dağılımı yok. MVP-2 için aynı disiplin uygulandı mı?

## Kaynaklar

- [docs/strategy/risk-register.md §4 (cut-list — Faz 0/1/2/3/4/5/6)](../../docs/strategy/risk-register.md)
- [docs/strategy/risk-register.md §4.9 (MVP-1 final scope)](../../docs/strategy/risk-register.md)
- [docs/product/information-architecture.md §13](../../docs/product/information-architecture.md) — Faz haritası
