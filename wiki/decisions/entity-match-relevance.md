---
type: decision
title: "Entity match relevance — content_generator alaka kuralı"
slug: "entity-match-relevance"
category: "rag-prompt"
status: "live"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/prompts/content_generator.py§106-156"
  - "GitHub Issue #623 / PR #630 (sıkı versiyon)"
  - "GitHub Issue #623 PR-E.2 / PR #633 (rebalanced)"
tags: ["rag", "prompt", "anti-hallucination", "mvp-1-8"]
aliases: ["alaka-check", "irrelevant-sources"]
---

# Entity match relevance

> **TL;DR:** content_generator prompt'ta "ALAKA KONTROLÜ" kuralı. Kategorik benzerlik (sergi/sergi) yetmez ama kelime kelime tam eşleşme de aşırı sıkı. **ANA KONU + KEY ENTITY'lerin EN AZ BİRİ** kart'larda geçmeli. Eşleşmiyorsa LLM `posts=[]`, `warnings=["irrelevant_sources"]` döndürür → kullanıcı "yetersiz veri" görür.

## Bağlam — iki ucta hatalı denemeler

**v1 (PR #630, PR-D)** — KELİMESİ KELİMESİNE eşleşme zorunluydu:
- ✅ Toprakaltı sergisi → Slovenya tüneli REJECTED (entity yok)
- ❌ "21 ülke F-16 radarları kim kazandı" → Northrop Grumman article
  REJECTED (entity tam eşleşmedi, "21 ülke" vs "21 ülkenin")
- Kullanıcı feedback: F-16 yetersiz veri (önceden çalışıyordu)

**v2 (PR #633, PR-E.2)** — yumuşatıldı:
- ANA KONU + KEY ENTITY'lerin EN AZ BİRİ eşleşmeli
- Synonym/abbreviation OK (TB3 ≈ TB-3)
- Parçalı eşleşme OK ("21 ülke F-16 radar" → "F-16 radar" yeter)

## Kural

```
EŞLEŞME KRİTERİ:
✅ ANA KONU + 1+ KEY ENTITY kart'larda geçiyorsa → ALAKALI
✅ Synonym/abbreviation OK
✅ Parçalı eşleşme OK
❌ Sadece KATEGORİ ortak (sergi/sergi) → ALAKASIZ
❌ Hiçbir entity geçmiyor, sadece tema benzer → ALAKASIZ
```

## Yasaklar

```
❌ Kategori ortaksa "alakalı" demek (sergi/sergi)
❌ UYDURMA başlık + ilgisiz kart toplama
   (Toprakaltı sergi sorusu + Slovenya tüneli + uydurma "Toprakaltı
    Sergileri ve Kültürel Etkinlikler" başlığı KESİN HAYIR)
❌ "Yarım bilgi de olsa cevap üreteyim"
```

## Etki — üretim vakaları

| Sorgu | Kart | Eşleşme | Sonuç |
|---|---|---|---|
| F-16 21 ülke kim kazandı | Northrop Grumman 21 ülke F-16 radar | F-16+21+radar match | ✅ ALAKALI |
| Toprakaltı sergisi | Slovenya tünel sergi | sadece "sergi" kategori | ❌ ALAKASIZ |
| Toprakaltı sergisi | İstanbul Toprakaltı Sergisi | "Toprakaltı" entity | ✅ ALAKALI |
| iPhone 17 | Samsung Galaxy yapay zeka | hiç entity yok | ❌ ALAKASIZ |

## İlişkiler

- [[multi-query-rewrite]] — retrieval geniş arama yapar, prompt sonra elemeler
- [[multi-source-synthesis]] — alakalı kartlar üzerinde sentez
- [[hyde-feature-flag]] — opsiyonel ek varyant

## Kaynaklar

- `apps/api/app/prompts/content_generator.py` §106-156
- [PR #630](https://github.com/selmanays/nodrat/pull/630) — sıkı versiyon
- [PR #633](https://github.com/selmanays/nodrat/pull/633) — rebalance
