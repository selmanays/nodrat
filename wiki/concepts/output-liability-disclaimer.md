---
type: concept
title: "Output liability disclaimer — LLM çıktı yasal sorumluluk"
slug: "output-liability-disclaimer"
category: "legal-policy"
status: "live"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docs/legal/tos.md §6 Üretilen İçerik ve Kullanıcı Sorumluluğu"
  - "docs/legal/tos.md §10 Sorumluluk Reddi"
  - "docs/legal/compliance-brief.md §6 Output Liability"
tags: ["legal", "llm", "liability", "disclaimer", "fsek"]
---

# Output Liability Disclaimer

> **TL;DR:** Nodrat LLM çıktıları **kullanıcının sorumluluğunda**. Nodrat haber kaynağı değildir; üretilen içeriği yayınlamadan önce kullanıcı doğrulamak zorundadır. Halüsinasyon riski açıkça beyan edilir.

## Konseptin İçeriği

LLM-tabanlı üretim üç ayrı sorumluluk katmanı içerir:

1. **Halüsinasyon riski** — DeepSeek/Claude bazen gerçek dışı bilgi üretir
2. **Telif uyumu (FSEK)** — 25 kelime cap'i içeride uygulanır ama kullanıcı yayınlama öncesi check
3. **Yanlış tarih/yer/kişi atfı** — date disambiguation eksikliği (#673), Wikipedia uydurma riski (#677)

## ToS §6 ve §10 Maddeleri

- **§6:** "Üretilen içerik kullanıcı tarafından review edilmeli ve yayınlamadan önce doğrulanmalıdır."
- **§10:** "Nodrat halüsinasyon, yanlış atıf, eksik bilgi nedeniyle doğacak zararlardan sorumlu değildir."

## Mitigation'lar (ürün tarafı)

- **Citation zorunlu** — her iddia için kaynak link gösterilir (sources array)
- **Insufficient_data response** — yetersiz veri varsa üretim yapma (boş cevap yerine 422)
- **Halüsinasyon yasağı** — Wikipedia ortak bilgiyi uydurma sıkı dilbilim (#677)
- **Citation validator** — atıf cosine sim ≥ 0.55 zorunlu (#180)
- **Warnings array** — kanıtsız iddia uyarısı kullanıcıya gösterilir
- **18+ yaş gate** — reşit sorumluluğu gerekçesiyle ([[age-gate-18-plus]])

## Kullanıcı Eğitimi

- Onboarding'de halüsinasyon risk uyarısı gösterilir
- Generate sayfasında "review before publish" CTA
- Saved generations sayfasında kullanıcı revize edebilir

## İlişkiler

- [[tos-md]] §6 + §10
- [[compliance-brief-md]] §6
- [[twenty-five-word-quote-cap]] — FSEK
- [[pii-redaction-mandatory]] — privacy
- [[age-gate-18-plus]] — reşit sorumluluk

## Kaynaklar

- [docs/legal/tos.md](../../docs/legal/tos.md) §6, §10
- [docs/legal/compliance-brief.md](../../docs/legal/compliance-brief.md) §6
