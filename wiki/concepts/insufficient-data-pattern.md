---
type: concept
title: "Insufficient_data response pattern — halüsinasyon önleme"
slug: "insufficient-data-pattern"
category: "rag"
status: "live"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docs/product/prd.md §2 Ana Hedefler (halüsinasyon yasağı)"
  - "docs/engineering/prompt-contracts.md §8 Hata Yönetimi"
  - "docs/engineering/api-contracts.md §11.1 (422 INSUFFICIENT_DATA)"
  - "GitHub Issue #670 / #674 / #677"
tags: ["rag", "prompt", "hallucination", "insufficient-data", "anti-pattern"]
---

# Insufficient_data Response Pattern

> **TL;DR:** Veri yetersiz olduğunda LLM **uydurma yapmaz**, sıfır çıktı + `INSUFFICIENT_DATA` 422 yanıt verir. Wikipedia ortak bilgi uydurma yasak (#677). API'de standartlaştırılmış pattern + UI feedback.

## Konsept

Halüsinasyon önleme RAG'da tek başına yeterli değil — LLM eğitim verisinden "akıl yürütüp" gerçek dışı bilgi üretebilir. Insufficient_data pattern bu riski tetikleyici prompt + API standartı ile kapatır.

## Tetikleyiciler (LLM bunlardan birinde reddetmeli)

1. **Retrieval boş** — agenda_card_count < 1 OR chunk_count < 1
2. **Retrieval düşük** — agenda_card_count < 2 (multi-source synthesis için minimum)
3. **Date disambiguation eksik** — sorgu spesifik tarih içerir, retrieval o tarih için kanıt yok (#673)
4. **Meta-sorgu** — kullanıcı niş röportaj/söz arıyor ama context bulunamıyor (#669)
5. **Halüsinasyon trap** — Wikipedia ortak bilgi sorgusu (Türkiye nüfusu vs.) — uydurma yasak (#677)

## Prompt Rules (prompt-contracts.md §8)

```text
RULE 1: Retrieved context boşsa veya yetersizse,
        "insufficient_data" status DÖN. Kendi bilgiden ÜRETMI.

RULE 2: Halüsinasyon RİSKİ varsa
        (Wikipedia ortak bilgi, eski tarih, atfı olmayan iddia),
        REDDET. "Bu sorgu için yeterli kaynak bulunamadı" mesajı.

RULE 3: Citation YOKSA iddiayı YAZMA.
        Her cümle bir [#N] kaynağa bağlı olmalı.
```

## API Yanıtı (api-contracts.md §11.1)

```json
{
  "code": "INSUFFICIENT_DATA",
  "title": "Veri yetersiz",
  "detail": "Bu konu için seçilen dönemde yeterli güvenilir haber verisi bulunamadı.",
  "data_coverage": { "agenda_card_count": 1, "minimum_required": 2 },
  "suggestions": [
    { "label": "Zaman aralığını genişlet (son 14 gün)", "params": { "mode_hint": "weekly" } }
  ]
}
```

UI suggestion CTA'ları kullanıcıya çözüm önerir (zaman genişletme, farklı keyword).

## Production İstatistikler (admin /admin/rag/pipeline-comparison)

- `insufficient_data_rate` admin dashboard'da takip edilir
- Hedef: < %5 (üretim isteklerinin)
- %5+ → ürün UX iyileştirme (daha iyi sorgu suggestion, query planner improvement)

## Kaynaklı PR'lar

- #670 cevapsızlık/eksiklik fix
- #673 date disambiguation
- #674 SUMMARY chunks-aware
- #677 KRİTİK halüsinasyon yasağı

## İlişkiler

- [[prd-md]] §2 Ana Hedefler
- [[prompt-contracts-md]] §8
- [[api-contracts-md]] §11.1
- [[pipeline-optimization]] — retrieval iyileştirme
- [[chunks-always-on-fallback]] — chunks > 0 fallback
- [[multi-source-synthesis]] — 2+ source agreement

## Kaynaklar

- [docs/product/prd.md](../../docs/product/prd.md) §2
- [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) §8
