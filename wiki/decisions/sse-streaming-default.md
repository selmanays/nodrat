---
type: decision
title: "SSE streaming default — /app/generate-stream"
slug: "sse-streaming-default"
status: "locked"
decided_on: "2026-05-09"
decided_by: "founder"
created: "2026-05-09"
updated: "2026-05-09"
sources:
  - "apps/api/app/api/app_generate_stream.py"
  - "apps/api/app/providers/deepseek.py"
  - "docs/engineering/api-contracts.md§11.2b"
  - "wiki/topics/pipeline-performance-baseline.md"
  - "GitHub Issue #527 / PR #528"
tags: ["locked-decision", "performance", "ux", "mvp-2.2"]
aliases: ["streaming-tttf", "sse-default"]
---

# SSE streaming default — `/app/generate-stream`

> **Karar:** İçerik üretiminde Time-To-First-Token (TTFT) hedefi <1s; bunu sağlamak için `/app/generate-stream` SSE endpoint'i frontend'in default akışı oldu. Eski blocking `POST /app/generate` JSON endpoint'i backward-compat için aynen korunur.
> **Durum:** locked
> **Tarih:** 2026-05-09 (PR [#528](https://github.com/selmanays/nodrat/pull/528) merged)

## Bağlam

`/app/generate` boru hattının baseline'ı 5-7s P95 ([[pipeline-performance-baseline]]) — kalite kaybı değil, mimari bekleme: DeepSeek `stream:false` + FastAPI blocking JSON response. Kullanıcı submit'ten sonra ~5s blank page görüyordu. Perplexity benzeri "anında yazmaya başlama" UX'i için stream + paralelleştirme zorunluydu.

İki yaklaşım vardı:

1. **Sahte hız (rejected):** spinner + skeleton + aşama mesajları; kullanıcı bekliyor ama "ilerliyor" hissi. UX kararsız, **gerçek beklemeyi gizlemiyor**.
2. **Gerçek streaming (selected):** DeepSeek tokenları SSE üzerinden frontend'e doğrudan akıt; post-by-post incremental render; citation/image post-stream paralel — kullanıcı 600-800ms'de ilk tokenı görüyor.

Karar #2: gerçek streaming. Sahte UX disiplin dışı, ölçülebilir TTFT < 1s P95 hedefi netti.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Tek-call streaming + final event'te full structured | Backward-compat kolay | Frontend partial JSON parse karmaşık | reddedildi |
| NDJSON format prompt'a (her post bir line) | Stream-friendly format | PROMPT_VERSION major bump + eval regression riski; system prompt v1.1.0 stable | reddedildi (gelecekte revisable) |
| **Server-side incremental JSON parser + post-by-post emit** | Prompt korunur, frontend lifecycle basit | Backend brace-matching state machine kompleksitesi | **seçildi** |
| Eski endpoint'i deprecate et | Maintenance basitleşir | Admin panel + diğer flow'lar bozulur | reddedildi (eski endpoint korunur) |

## Mimari değişiklikler (locked)

- **DeepSeekProvider.generate_text_stream:** `stream:true` + `stream_options.include_usage:true`. Final chunk usage + cost dolu; cost tracking eski path ile birebir aynı.
- **StreamingPostExtractor** ([[streaming-json-parser]]): incremental brace-aware JSON parser, `posts[N]` objelerini tamamlanır tamamlanmaz emit eder. Edge case'ler: chunk boundary, escape edilmiş tırnak, string içinde `}`.
- **Speculative retrieval** ([[speculative-retrieval]]): `embed(raw_query)` planner ile paralel başlar; raw≈enriched ise embedding reuse, aksi halde re-embed (~150-300ms net kazanç).
- **Planner cache** ([[planner-cache]]): Redis 24h TTL, gün granülasyonu; cache hit'te ~10ms, miss eski davranış.
- **Citation + image post-stream:** `asyncio.gather` paralel; FSEK 25-kelime + halü kontrol gate'leri korunur, kullanıcının ilk byte'ını bloklamaz.

## Sonuçlar

- Hangi varlık/kavramları etkiler: [[deepseek]] (streaming kapasitesi), [[planner-cache]] (yeni concept), [[speculative-retrieval]] (yeni concept), [[streaming-json-parser]] (yeni concept).
- Etki kapsamı: [[pipeline-performance-baseline]] MVP-2.2 satırı; [[data-pipelines]] /app/generate akışı (yeni event sequence).
- API contract: [docs/engineering/api-contracts.md §11.2b](../../docs/engineering/api-contracts.md) — yeni endpoint kanonik tanım.
- Frontend: `useGenerationStream` hook + `StreamingPreview` component → `/app/generate` page'i artık SSE consumer.
- Eski endpoint korunur (geriye uyumluluk): admin panel preview + diğer flow'lar değişmez.

## Kalite gate korunması (kritik)

Bu karar performans optimizasyonu olduğu için legal/quality gate'lerin **hiçbiri kompromise edilmedi**:

- **FSEK 25-kelime cap** ([[twenty-five-word-quote-cap]]): system prompt değişmedi (v1.1.0 stable), validator aynı.
- **Halü kontrol** (R-LLM-01): `validate_citations_batch` post-stream çalışır; halu_flag_rate metric'i etkilenmez.
- **PII redaction** ([[pii-redaction-mandatory]]): provider streaming path'te de aktif (DeepSeekProvider.generate_text_stream redact uygular).
- **Cost tracking** (R-FIN-01): final chunk'ta `usage` dolu; `provider_call_logs` eski path ile birebir aynı kayıt.

## Implementation gotcha'ları (post-deploy hotfix #531)

İlk deploy sonrası **token-by-token akış görünmedi** — content tamamı tek seferde geldi. Üç katman birden buffer'lıyordu:

1. **Caddy `encode gzip zstd`** — varsayılan compression tüm response'lara uygulanıyor; SSE chunks compression buffer'ında biriktiriyor. Fix: named matcher ile bypass.
   ```
   @notSse not path /api/app/generate-stream*
   encode @notSse gzip zstd
   ```
2. **Caddy reverse_proxy default flush** — yetersiz; her chunk anında forward edilsin diye explicit `flush_interval -1` gerek.
3. **Backend `Cache-Control: no-cache`** — nginx ekosisteminde yetiyor, Cloudflare/Caddy `no-transform` direktifini de bekliyor; ek olarak `Content-Encoding: identity` ile compression bypass garantisi.

Bu hotfix #531/PR #532'de uygulandı. **Manuel deploy disiplini olarak çıkarımlar:**

- Backend code change → `docker compose build --no-cache <service>` (cache'li layer aynı kodla rebuild görmez)
- Caddyfile change → `docker compose up -d --force-recreate caddy` (bind mount alone yenilemez; container recreate)
- Her iki durumda: `docker exec <container> grep <change-token> /path` doğrulama zorunlu.

## Geri alma maliyeti

Düşük: `/app/generate` eski endpoint zaten duruyor. Frontend'i `useGenerationStream` yerine eski `generate` fn'e döndürmek tek dosya değişikliği. Backend SSE endpoint'i de feature flag arkasına alınabilir (`settings.streaming_enabled=False` → 404 dönsün — ama şu an böyle bir flag yok, gerekirse eklenir).

PR [#528](https://github.com/selmanays/nodrat/pull/528) revert etmek mümkün; mid-stream parser regression çıkarsa kullanıcı doğrudan eski endpoint'e fall-back için frontend tarafında `try { generateStream } catch { generate }` pattern'i sonraki iterasyonda kolayca eklenir.

## İlişkiler

- **İlgili kararlar:** [[deepseek-default-llm]] (streaming kapasitesi notu eklendi), [[twenty-five-word-quote-cap]], [[pii-redaction-mandatory]] (her ikisi de stream path'te aktif)
- **İlgili varlıklar:** [[deepseek]] (provider streaming desteği)
- **İlgili kavramlar:** [[planner-cache]], [[speculative-retrieval]], [[streaming-json-parser]]
- **İlgili topics:** [[pipeline-performance-baseline]] (MVP-2.2 row), [[data-pipelines]] (P6 /app/generate event sequence)
- **İlgili risk:** R-FIN-01 (cost runaway — etkilenmez, token miktarı aynı), R-LLM-01 (halü — gate korunur)

## Açık sorular / TODO

- `done` event'indeki `ttfb_ms` `provider_call_logs`'a kalıcı kolon olarak eklenmedi; sonraki iterasyon `/admin/rag` Performans sekmesinde TTFB P95 görünür olacak.
- Mid-stream provider hata recovery (caller restart) sonraki tur — şu an tek attempt; pre-stream 429/5xx için retry zaten var.
- Claude Haiku streaming MVP-3 Faz 6'da Pro tier ile birlikte (ayrı iş).
