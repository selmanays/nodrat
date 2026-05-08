---
type: entity
title: "Style Profile System (Faz 5)"
slug: "style-profile-system"
category: "service"
status: "live"
created: "2026-05-09"
updated: "2026-05-09"
sources:
  - "docs/product/prd.md§5"
  - "docs/engineering/data-model.md§7.1"
  - "docs/engineering/data-model.md§7.2"
  - "docs/engineering/api-contracts.md§12"
  - "docs/engineering/prompt-contracts.md§5.1"
tags: [faz-5, pro-tier, llm, paywall, style]
aliases: ["stil profili", "style-profiles"]
---

# Style Profile System (Faz 5)

> **TL;DR:** Pro+ kullanıcıların kendi yazı stilini sisteme öğreten servis. 3-50 örnek metinden DeepSeek V3 Style Analyzer ile JSON `rules_json` çıkarır; `/app/generate` bu kuralları content prompt'una geçirir. Free/Starter tier'a 402, Pro=3 / Agency=10 slot quota.

## Tanım

İki tablodan oluşan kalıcı stil tanımı + 1 Celery analyzer task + Pro paywall + generation entegrasyonu.

| Bileşen | Konum |
|---|---|
| `style_profiles` tablosu | Migration `20260509_0700`; PRD §5.6 + status/error_message kolonu eklendi |
| `style_samples` tablosu | Migration `20260509_0700`; cascade delete + char_count kolonu |
| Style Analyzer prompt | `app/prompts/style_analyzer.py` v1.0.0 — JSON-mode, 80k toplam karakter limit |
| Celery task | `tasks.style_profile.analyze` (event_queue), max_retries=2 |
| API router | `/app/style-profiles` (POST/GET/DELETE/POST samples/POST reanalyze) |
| Pro paywall | server-side `_resolve_style_profile` + `_check_paywall` |
| Generation entegrasyonu | `GenerateRequest.style_profile_id` → render_payload `style_profile=rules_json` |
| Frontend | `/app/style-profiles` list + detail + dialog + generate dropdown |

## Nodrat'ta kullanım

- Pro tier: 3 slot, Agency: 10 slot (plan.features `style_profiles_slots`)
- Free/Starter: 402 STYLE_PROFILES_REQUIRES_PRO (server-side)
- Generation flow'da seçilince `Generation.style_profile_id` FK persist edilir, prompt'ta Rule 11 (`style_profile verildiyse rules_json'daki sentence_length, tone, rhetorical_patterns'a uy`).
- Status workflow: `pending → analyzing → ready / failed` (≥3 sample dolunca otomatik analyze; sample ekleme sonrası reanalyze)

## Önemli özellikler / parametreler

| Parametre | Değer | Kaynak |
|---|---|---|
| MIN_SAMPLES (analyze trigger) | 3 | style_analyzer.py |
| MAX_SAMPLES per profile | 50 | style_analyzer.py |
| MAX_SAMPLE_CHARS | 4000 | style_analyzer.py |
| MAX_TOTAL_CHARS (prompt budget) | 80 000 | style_analyzer.py |
| Provider | DeepSeek V3 (registry tier=free) | tasks/style_profile.py |
| max_tokens / temperature | 2000 / 0.2 | tasks/style_profile.py |
| PII redaction | sample import + analyze çağrısı (KVKK) | api/style_profiles.py + provider |

## Status workflow

```
pending      ──(N≥3 örnek)──>  analyzing  ──(LLM ok + parse ok)──>  ready
   │                              │
   │                              ├──(LLM error)──>  failed (autoretry 2x)
   │                              └──(parse error)─> failed (manual reanalyze)
   │
   └──(N<3)──> pending kalır (kullanıcı sample eklesin)
```

## Kararlar (locked)

- [[style-profiles-pro-paywall]] — Faz 5 paywall + slot quota disiplini
- [[lemon-squeezy-payment-provider]] — Pro+ subscription gate (plan.features.style_profiles)
- [[pii-redaction-mandatory]] — sample import path

## İlişkiler

- Bağımlı: [[deepseek|DeepSeek (default LLM)]] — analyzer provider
- Kullanılır: [[provider-abstraction]] — registry.route_for_tier
- Analyzer prompt: [[style-analyzer-prompt]]
- Tetikleyici: PRD §5 (Faz 5)

## Açık sorular / TODO

- A/B retention impact ölçümü (kabul kriteri "[ ] Pro retention A/B sonucu") — telemetry layer launch sonrası
- CSV import endpoint — şu an `csv_import` source_type tanımlı ama dedicated bulk endpoint yok; sample/POST tek tek ile çalışır
- X personal hesap import — `x_personal` source_type tanımlı, X API entegrasyonu yok (#52 PRD §5.2 hukuki risk notu)

## Kaynaklar

- [docs/product/prd.md §5](../../docs/product/prd.md)
- [docs/engineering/data-model.md §7.1-7.2](../../docs/engineering/data-model.md)
- [docs/engineering/api-contracts.md §12.1-12.3](../../docs/engineering/api-contracts.md)
- [docs/engineering/prompt-contracts.md §5.1](../../docs/engineering/prompt-contracts.md)
- PR #512 (backend), #514 (text() shadow hotfix), #516 (frontend), #518 (build hotfix)
