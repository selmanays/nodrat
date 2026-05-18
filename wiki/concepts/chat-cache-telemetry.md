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

> **TL;DR:** Generate-hattı her chat LLM çağrısı için izole `chat_cache_telemetry` tablosuna prompt-cache segment ölçümü yazılır (#981); `/admin/rag` "Önbellek" sekmesinden izlenir (#982); `call_type` kırılımı **Senaryo-B**'yi (#983) görünür kılar — forced-final `tool_choice` farkı (`none` ≡ tools-yok, kontrollü deneyle kanıtlı) DeepSeek cache-prefix'ini kırıyordu; #1006 iki-kademeli fix (`tool_choice="auto"` + bounded retry) çöküşü giderdi — empirik: forced_final cached 4608→30976 (davranış-nötr). Yalnız token **sayısı** tutulur (KVKK), best-effort + flag-gated (chat akışı ASLA kırılmaz).

## Bağlam — neden var

Tek 5-soruluk sohbet tanısı (conv `b20055ac`) gösterdi: (a) loglanan cost yanlış sabitlerle hesaplanıyordu → [[deepseek-default-llm|DeepSeek pricing yanılgısı]] #990 ile temizlendi (v4-flash $0.14/$0.0028/$0.28, indirim YOK); (b) %55.7 cache-miss'in büyük kısmı yapısal (her soruda yeni RAG dokümanı, ilk-gönderim daima miss); (c) **forced-final** çağrısı (agentic döngü tükenince) `tools`/`tool_choice`'u düşürüyordu → DeepSeek payload'ında `tools` yok → cache-prefix 0. token'dan kırılıyor (kanıt: call8/15 `cached=4608` collapse vs aynı turun tool-round'u 14336/16384; doğal-final call11 30848). Telemetri olmadan bu kör — `provider_call_logs` token TOPLAMINI tutar ama KOMPOZİSYONU değil.

## Üç teslimat

1. **#981 — `chat_cache_telemetry` tablo + writer.** İzole tablo (billing `usage_events`'e / RAG-oluşturma'ya dokunmaz). Writer kurşungeçirmez best-effort (kendi session, çift-korumalı, exception yutar) + runtime flag `observability.chat_cache_enabled` (default true; deploy'suz kapatılır). `_tracked_chat_generate`'e `conv_id`/`call_type` eklendi; loop=`tool_round`, forced-final=`forced_final`. v1 segment ayrımı kaba (5-kova ≈chars/4; fatura DEĞİL). condense/`_generate_followups` bilinçli fast-follow (blast-radius). Migration `20260518_0200` (additive, zero-downtime).
2. **#982 — `/admin/rag` "Önbellek" sekmesi.** `GET /admin/rag/cache-telemetry` (require_admin, parametreli SQL): `call_type` kırılımı + segment ortalaması + opsiyonel `user_id` drill-down. **$ VERMEZ** (token-bazlı, fiyat-bağımsız — maliyet-yanılgısı dersi; gerçek $ ayrı `provider_call_logs.cost_usd`). [[pipeline-observability-location]] locked decision'a uyumlu: yeni sayfa/observability AÇILMADI, `/admin/rag` sekmesi. Hotfix #1001: `:uid` asyncpg `AmbiguousParameterError` → `CAST(:uid AS uuid) IS NULL` (auth'lu yolun test boşluğu; ders → memory).
3. **#983 (yanlış teşhis) → #1006 (kök fix).** #983 forced-final'e `tool_choice="none"` ekledi — empirik **başarısız** (forced_final yine cached=4608). **Kontrollü deney (api container, izole değişken) kök sebebi KANITLADI:** DeepSeek `tool_choice="none"` → tools şemasını prompt'a HİÇ koymaz (`none`+tools input **8066** == tools-YOK **8066**; `auto`+tools **8345**; `auto`↔`none` switch cached=**0**). Yani `none` ≡ tools-yok → forced-final prefix'i tool_round'dan (auto+tools) baştan ayrışır → cache çöker. **#1006 iki-kademeli bounded fix:** Kademe-1 forced-final `tools=tools_arg, tool_choice="auto"` (= kanıtlı doğal-final şekli; prefix tool_round ile eşleşir) + güçlü #860 nudge (tool'u API değil prompt engeller); Kademe-2 nadir güvenlik — model yine tool çağırırsa TEK retry `tool_choice="none"` (`call_type='forced_final_retry'`). Sonsuz döngü YOK (forced-final döngü dışı tek atış). C1 backstop zaten `continue`→loop ile tools korur (dokunulmadı).

## Empirik kanıt (gerçek production trafiği)

**#990/#981 + cevap-kalitesi (session `86f565c9`, aynı 5 soru):**

| | Orijinal `b20055ac` | Yeni `86f565c9` |
|---|---|---|
| loglanan cost | $0.013933 (YANLIŞ pricing) | **$0.010190** (DOĞRU — v4-flash aritmetiği birebir) |
| genel cache-hit | %44.3 | **%53.6** |
| Türkiye/TRT cevabı | ❌ "kaynakta yok" | ✅ "TRT 1 / 14 Nisan 2007" + citation |

→ #990 pricing + #981 telemetri (11 organik `tool_round`) + cevap-kalitesi **doğrulandı**.

**#1006 forced-final cache fix (session `088cfb46`, döngü-tüketen sorgu):**

| forced_final | input | **cached** | **cache-hit** |
|---|---|---|---|
| `7b2be57c` (fix ÖNCESİ) | 47.876 | **4.608** | **%9.6** ❌ çöküş |
| `088cfb46` (#1006 SONRASI) | 44.969 | **30.976** | **%68.9** ✅ |

→ forced_final cache çöküşü **çözüldü**: cached 4.608→**30.976**, hit %9.6→**%68.9** (aynı sohbet tool_round %54.5'ten yüksek — en çok birikmiş bağlamı taşır). `forced_final_retry` HİÇ tetiklenmedi (Kademe-1 auto+nudge yetti). Davranış korundu (uydurma sorgu dürüstçe reddedildi, halü yok). "Bulamadım" sorgu maliyeti **~yarıya** indi ($0.011→$0.0058).

## Açık / fast-follow

- condense + `_generate_followups` untracked çağrıları (ayrı issue) — Senaryo-B için gereksiz.
- Segment fine-split (msg1 static/history/question) — v1 kaba; şema kolonları forward-compat hazır.
- ✅ ÇÖZÜLDÜ: #983 yanlış teşhis → #1006 (kontrollü deney + iki-kademeli fix) → forced_final cached 4608→30976 (%9.6→%68.9) empirik kanıtlandı (session 088cfb46).

## İlişkiler

- [[pipeline-observability-location]] — panel yeri locked decision (`/admin/rag` sekme; bu telemetri ona uyar)
- [[deepseek-default-llm]] — v4-flash pricing (#990 yanılgı purge; cache hit/miss maliyet bağlamı)
- [[extraction-confidence-telemetry]] — kardeş telemetri deseni (best-effort, runtime-flag, izole)

## Kaynaklar

- [docs/engineering/data-model.md §4.6](../../docs/engineering/data-model.md) — `chat_cache_telemetry` DDL
- [docs/engineering/api-contracts.md §10.4.1](../../docs/engineering/api-contracts.md) — `GET /admin/rag/cache-telemetry`
- GitHub: #981 (tablo+writer), #982 (panel), #983 (forced-final ilk-fix — yanlış teşhis), #1001 (uid hotfix), #1006/#1007 (kök fix — kontrollü deney + iki-kademeli, empirik kanıtlı), epic #980
