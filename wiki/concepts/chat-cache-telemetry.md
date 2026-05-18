---
type: concept
title: "Chat prompt-cache segment telemetri + Senaryo-B forced-final fix"
slug: "chat-cache-telemetry"
category: "metric"
status: "live"
created: "2026-05-18"
updated: "2026-05-18"
sources:
  - "docs/engineering/data-model.md§4.6"
  - "docs/engineering/api-contracts.md§10.4.1"
tags: ["telemetry", "prompt-cache", "deepseek", "observability", "mvp-1-8"]
aliases: ["cache-telemetry", "forced-final-cache-fix", "senaryo-b"]
---

# Chat prompt-cache segment telemetri + Senaryo-B forced-final fix

> **TL;DR:** Generate-hattı her chat LLM çağrısı için izole `chat_cache_telemetry` tablosuna prompt-cache segment ölçümü yazılır (#981); `/admin/rag` "Önbellek" sekmesinden izlenir (#982); `call_type` kırılımı **Senaryo-B**'yi (#983) görünür kılar — forced-final çağrısı `tools`'u düşürünce DeepSeek cache-prefix'i 0. token'dan kırılıyordu, fix `tools=tools_arg, tool_choice="none"` ile cache'i korur (davranış-nötr). Yalnız token **sayısı** tutulur (KVKK), best-effort + flag-gated (chat akışı ASLA kırılmaz).

## Bağlam — neden var

Tek 5-soruluk sohbet tanısı (conv `b20055ac`) gösterdi: (a) loglanan cost yanlış sabitlerle hesaplanıyordu → [[deepseek-default-llm|DeepSeek pricing yanılgısı]] #990 ile temizlendi (v4-flash $0.14/$0.0028/$0.28, indirim YOK); (b) %55.7 cache-miss'in büyük kısmı yapısal (her soruda yeni RAG dokümanı, ilk-gönderim daima miss); (c) **forced-final** çağrısı (agentic döngü tükenince) `tools`/`tool_choice`'u düşürüyordu → DeepSeek payload'ında `tools` yok → cache-prefix 0. token'dan kırılıyor (kanıt: call8/15 `cached=4608` collapse vs aynı turun tool-round'u 14336/16384; doğal-final call11 30848). Telemetri olmadan bu kör — `provider_call_logs` token TOPLAMINI tutar ama KOMPOZİSYONU değil.

## Üç teslimat

1. **#981 — `chat_cache_telemetry` tablo + writer.** İzole tablo (billing `usage_events`'e / RAG-oluşturma'ya dokunmaz). Writer kurşungeçirmez best-effort (kendi session, çift-korumalı, exception yutar) + runtime flag `observability.chat_cache_enabled` (default true; deploy'suz kapatılır). `_tracked_chat_generate`'e `conv_id`/`call_type` eklendi; loop=`tool_round`, forced-final=`forced_final`. v1 segment ayrımı kaba (5-kova ≈chars/4; fatura DEĞİL). condense/`_generate_followups` bilinçli fast-follow (blast-radius). Migration `20260518_0200` (additive, zero-downtime).
2. **#982 — `/admin/rag` "Önbellek" sekmesi.** `GET /admin/rag/cache-telemetry` (require_admin, parametreli SQL): `call_type` kırılımı + segment ortalaması + opsiyonel `user_id` drill-down. **$ VERMEZ** (token-bazlı, fiyat-bağımsız — maliyet-yanılgısı dersi; gerçek $ ayrı `provider_call_logs.cost_usd`). [[pipeline-observability-location]] locked decision'a uyumlu: yeni sayfa/observability AÇILMADI, `/admin/rag` sekmesi. Hotfix #1001: `:uid` asyncpg `AmbiguousParameterError` → `CAST(:uid AS uuid) IS NULL` (auth'lu yolun test boşluğu; ders → memory).
3. **#983 — forced-final cache fix.** Tek nokta: forced-final `_tracked_chat_generate` çağrısına `tools=tools_arg, tool_choice="none"`. tools schema prefix'te kalır (cache eşleşir), `tool_choice="none"` API-kontratıyla tool çağrısını yasaklar → davranış mevcut "tools-yok + #860 nudge" ile aynı/daha güçlü. C1 backstop zaten `continue`→loop ile tools koruyor (dokunulmadı).

## Empirik kanıt (yeni session `86f565c9`, aynı 5 soru)

| | Orijinal `b20055ac` | Yeni `86f565c9` |
|---|---|---|
| loglanan cost | $0.013933 (YANLIŞ pricing) | **$0.010190** (DOĞRU — v4-flash aritmetiği birebir) |
| input token | 291.813 | 213.762 |
| genel cache-hit | %44.3 | **%53.6** |
| forced_final | 2 (cached=4608 collapse) | **0 (tetiklenmedi)** |
| Türkiye/TRT cevabı | ❌ "kaynakta yok" | ✅ "TRT 1 / 14 Nisan 2007" + citation |

#990 pricing + #981 telemetri (11 organik `tool_round`, `tools_present=1`, hit %54.1) + cevap-kalitesi **empirik doğrulandı**. #983 fix kod-canlı (`FIX_LIVE=True`) ama bu run forced_final tetiklemedi → spesifik "forced_final collapse gitti" empirik ispatı döngü-tüketen bir run bekliyor (genel cache zaten %44→%54 iyileşti).

## Açık / fast-follow

- condense + `_generate_followups` untracked çağrıları (ayrı issue) — Senaryo-B için gereksiz.
- Segment fine-split (msg1 static/history/question) — v1 kaba; şema kolonları forward-compat hazır.
- #983 forced_final empirik kıyası — döngü-tüketen sorgu gelince telemetriden ölçülecek.

## İlişkiler

- [[pipeline-observability-location]] — panel yeri locked decision (`/admin/rag` sekme; bu telemetri ona uyar)
- [[deepseek-default-llm]] — v4-flash pricing (#990 yanılgı purge; cache hit/miss maliyet bağlamı)
- [[extraction-confidence-telemetry]] — kardeş telemetri deseni (best-effort, runtime-flag, izole)

## Kaynaklar

- [docs/engineering/data-model.md §4.6](../../docs/engineering/data-model.md) — `chat_cache_telemetry` DDL
- [docs/engineering/api-contracts.md §10.4.1](../../docs/engineering/api-contracts.md) — `GET /admin/rag/cache-telemetry`
- GitHub: #981 (tablo+writer), #982 (panel), #983 (forced-final fix), #1001 (uid hotfix), epic #980
