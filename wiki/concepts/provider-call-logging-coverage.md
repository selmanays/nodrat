---
type: concept
title: "DeepSeek call-site loglama kapsamı — her çağrı provider_call_logs'ta mı?"
slug: "provider-call-logging-coverage"
status: live
created: 2026-06-18
updated: 2026-06-18
sources:
  - "apps/api/app/shared/observability/cost_tracker.py (track_provider_call)"
  - "apps/api/app/providers/deepseek.py (generate_text → chat/completions)"
  - "docs/engineering/data-model.md §4.5 (provider_call_logs)"
  - "GitHub Issue #1602 / PR #1603 / Issue #1604 / PR #1605"
tags: ["observability", "cost", "deepseek", "provider-call-logs"]
aliases: ["deepseek-cost-coverage", "llm-call-logging"]
---

# DeepSeek call-site loglama kapsamı

> **TL;DR:** DeepSeek (paralı LLM) çağrıları `track_provider_call` context manager'ı ile `provider_call_logs` tablosuna (operation / token / cost_usd) loglanır. 2026-06-18 maliyet denetiminde (#1602) iki boşluk tespit edilip kapatıldı: NER eskiden hiç loglanmıyordu (#1533), research hattının 4 yardımcı çağrısı loglanmıyordu (#1604). Bugün tüm üretim DeepSeek call-site'ları loglanır.

## Neden önemli

Loglanmayan bir DeepSeek çağrısı = **görünmeyen maliyet**: DeepSeek'in kestiği fatura, panel toplamından yüksek olur. "Maliyet neden arttı" analizleri `provider_call_logs` gün × operation kırılımına dayanır; eksik loglama bu analizi sistematik olarak yanıltır. (Kullanıcı "her kullanım loglanıyor mu" sorusunun kalıcı cevabı bu sayfadır.)

## Loglanan operation envanteri (güncel)

| operation | call-site | tetikleyici | ne zamandan beri |
|---|---|---|---|
| `chat` | tracked_chat (research ana cevap) + agenda / raptor / style / country backfill | kullanıcı + beat | baştan |
| `ner` | `entities/tasks/entities.py` | beat / forward-pipeline | **#1533** (önce hiç yoktu) |
| `chunk_keywords` | `embedding/tasks/embedding.py` | forward-pipeline | #778 |
| `llm_rerank` | `core/rerank.py` | kullanıcı (retrieval) | baştan |
| `planner` | `prompts/query_planner.py` | her research (search_news) | **#1604** |
| `query_rewrite` | `prompts/query_rewrite.py` | bağlamlı takip | **#1604** |
| `decomposition` | `prompts/query_decomposition.py` | flag açıksa | **#1604** |
| `followup` | `modules/generations/followup.py` | her cevap sonrası | **#1604** |

> NIM tarafı (embedding bge-m3, vision VLM) DeepSeek **değil** — ücretsiz; yine de `operation='embedding'/'vision'` ile cost=0 loglanır.

## Kapatılan iki boşluk

- **NER (#1533):** `operation='ner'` ilk kez loglandı. Loglama görünür kılınca hemen ardından NER backfill **sonsuz döngüsü** ortaya çıktı (#1602) — entity-üretmeyen makaleler her 30dk yeniden çağrılıyordu. Detay: [[ner-pipeline]] §Maliyet güvenliği.
- **Research yardımcıları (#1604):** `plan_query` / `condense_followup_query` / `decompose_query_llm` / `_generate_followups` `track_provider_call` ile sarılmıyordu. Fix deseni: `generate_text`'e **dokunmadan**, çağrı sonrası **best-effort** cost-log (kendi kısa session + commit, `try/except: pass`) → loglama/DB çökse bile kullanıcı-facing research akışı bozulmaz. `latency_ms` bu çağrılarda ~0 loglanır (blok generate_text'i kapsamaz; token + cost doğru — asıl hedef).

## Maliyet panelleri / sorgu

- `/admin/dashboard/provider-calls` — çağrı **sayısı** (period 7d/30d/3m).
- `/admin/rag/pipeline-comparison` — **$ maliyet**/req (⚠️ `operation='research'` stale-filtresi yüzünden boş gösterebilir; gerçek maliyet `operation IN ('chat','ner',...)` satırlarında).
- Doğrudan SQL (en güvenilir): `SELECT operation, COUNT(*), SUM(cost_usd) FROM provider_call_logs WHERE created_at >= NOW() - INTERVAL '7 days' GROUP BY 1 ORDER BY 3 DESC;`

## İlişkiler

- [[ner-pipeline]] — NER call-site + #1602 backfill döngü fix
- [[pipeline-observability-location]] — maliyet panellerinin admin'deki yeri (locked)
- [[deepseek-default-llm]] — default chat provider routing
- [[variable-cost-uretim]] — birim üretim maliyeti
- [[data-model-md]] — `provider_call_logs` §4.5 şema

## Kaynaklar

- [`cost_tracker.py`](apps/api/app/shared/observability/cost_tracker.py) — `track_provider_call`
- [data-model.md §4.5](docs/engineering/data-model.md) — provider_call_logs operation envanteri
- [Issue #1602](https://github.com/selmanays/nodrat/issues/1602) / [Issue #1604](https://github.com/selmanays/nodrat/issues/1604)
