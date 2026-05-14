---
type: decision
title: "Multi-LLM per-operation routing (DeepSeek + Gemini cascade)"
slug: "multi-llm-per-op-routing"
status: "locked"
decided_on: "2026-05-14"
decided_by: "tech"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "docs/engineering/architecture.md§4"
  - "docs/engineering/prompt-contracts.md"
tags: ["locked-decision", "llm", "cost"]
aliases: ["llm-routing", "gemini-fallback", "deepseek-vs-gemma"]
---

# Multi-LLM per-operation routing

> **Karar:** 4 LLM operasyonu (NER, planner, rerank, generation) için per-operation provider seçimi admin /settings/llm'den runtime değişebilir. Default DeepSeek, alternatif Gemini (Gemma 4 26B/31B ücretsiz tier). Gemini quota tükenirse otomatik DeepSeek cascade.
> **Durum:** locked
> **Tarih:** 2026-05-14

## Bağlam

Kullanıcının talebi: "DeepSeek API'yi boş yere kullanmayalım eğer Gemma modellerinin çözebileceği işler varsa". Önceki yapıda her LLM çağrısı sabit DeepSeek (veya tier'a göre Claude Haiku) idi. Yeni gereksinim: per-operation tunable, Gemini Gemma 4 ücretsiz alternatif olarak.

Bulgular (#778 testleri):
- Gemma 4 26B JSON output kalitesi yüksek (production prompt'la)
- v1beta API'da `generateContent` destekleyen 2 Gemma model: 26B + 31B (Console'daki Gemma 3'ler 404)
- Toplam ücretsiz kapasite: 3000 request/gün (2 × 1500)
- Gemma 4 chain-of-thought reasoning üretiyor — robust JSON extractor şart
- thinkingBudget=0 Gemma 4'te 400 INVALID_ARGUMENT (Gemini 2.x'te çalışır)

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Tek provider (DeepSeek) | Basit, kaliteli | Gemma ücretsiz potansiyel kaybediliyor | reddedildi (cost odaklı) |
| Global LLM switch (admin tek setting) | Tek konfigürasyon | Per-op granülarite yok, generation kalite kritik | reddedildi |
| **Per-op routing + cascade** | Esnek, cost optimize, fallback safe | Kod karmaşıklığı, 7 admin key | **seçildi** |
| LangChain ChatModel abstraction | Hazır | 6+ dep ekler, mimari yabancı | reddedildi |

## Sonuçlar

### Routing mekanizması
- 4 setting key (`llm.routing.{ner,planner,rerank,generation}`) — admin /settings/llm dropdown
- Default tüm op'lar "deepseek", admin UI'dan "gemini" seçilebilir
- `resolve_chat_provider(db, op_name, tier)` async function: DB read → registry lookup → fallback

### Gemini provider entegrasyonu
- [`apps/api/app/providers/gemini.py`](apps/api/app/providers/gemini.py): Google Gemini API v1beta, `gemma-4-26b-a4b-it` default, `gemma-4-31b-it` premium
- Cost = $0 (ücretsiz tier), PII redaction user mesajlarına uygulanır
- Model cascade: 429 daily-quota → otomatik next model (26B → 31B → ProviderRateLimitError)
- Per-minute rate limit (15 RPM) ise exponential backoff retry aynı modelde

### Script-level cascade (backfill için)
- Backfill script `ProviderRateLimitError` yakalar → global provider DeepSeek'e geçer
- Sonraki chunk'lar DeepSeek ile kesintisiz devam
- Yarın quota reset → script restart → tekrar Gemini başlar

### Gemma JSON output handling
- Robust JSON extractor: code fence → last balanced object → raw passthrough
- Array wrap `[{...}]` → tek dict (`_coerce_dict`)
- Hem backfill hem worker (Celery extract_chunk_keywords) aynı parser

## Kullanım rehberi

| Operation | Önerilen | Neden |
|---|---|---|
| Bulk backfill (one-time 12K+) | **DeepSeek** | Quota + hız (~$2.50, ~1h paralel) |
| Runtime planner (per-query) | Gemini OK | Free, 1500/gün >> kullanım |
| Runtime rerank (3 chunk/gen) | Gemini OK | Free, latency 3s acceptable |
| Runtime generation | **DeepSeek** | Quality kritik, prod default |
| Per-article ingest NER | Gemini OK | Yavaş pipeline, free işe yarar |

## Geri alma maliyeti

> Tüm op'ları `deepseek`'e set et (admin /settings/llm). Gemini provider hâlâ registry'de (registered) ama route edilmez. `GOOGLE_API_KEY` env değişkeni kaldırılırsa Gemini bootstrap atlanır.

## Kaynaklar

- [`apps/api/app/providers/gemini.py`](apps/api/app/providers/gemini.py)
- [`apps/api/app/providers/registry.py`](apps/api/app/providers/registry.py) (`resolve_chat_provider`)
- [`apps/web/src/app/admin/settings/[group]/page.tsx`](apps/web/src/app/admin/settings/[group]/page.tsx) (SETTING_ENUM_CHOICES)
- PR [#779](https://github.com/selmanays/nodrat/pull/779)
