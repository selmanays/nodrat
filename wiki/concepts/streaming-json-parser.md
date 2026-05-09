---
type: concept
title: "Streaming JSON post extractor"
slug: "streaming-json-parser"
category: "architecture"
status: "live"
created: "2026-05-09"
updated: "2026-05-09"
sources:
  - "apps/api/app/core/streaming_json.py"
  - "apps/api/tests/unit/test_streaming_json.py"
  - "GitHub Issue #527 / PR #528"
tags: ["streaming", "json", "parser", "mvp-2.2"]
aliases: ["sse-json-parser", "post-extractor"]
---

# Streaming JSON post extractor

> **TL;DR:** DeepSeek `json_mode=True` response'ı chunk-by-chunk gelir. Bu parser accumulating buffer'dan **tamamlanmış `posts[i]` objelerini** erkenden tespit edip emit eder. String-aware brace matcher; chunk boundary post text ortasında düşse bile sonraki feed'de doğal devam eder.

## Bağlam

Content Generator çıktısı:

```json
{
  "posts": [
    {"text": "...", "angle": "...", "char_count": N, "related_agenda_card_ids": [...]},
    ...
  ],
  "summary": "...",
  "sources": [...]
}
```

DeepSeek streaming her chunk ~10-50 karakter delta gönderir. Tam JSON ancak son chunk'tan sonra parse edilebilir → o noktada **first byte UX'i kaybedildi**. Frontend tarafında her chunk'ı raw text olarak biriktirmek de mümkün ama kullanıcının "1. post tamamlandı, kart şimdi belirsin" deneyimi için backend'de **post-by-post emit** gerekir.

Bu parser bu boşluğu doldurur: tam streaming JSON parser değil — sadece **`posts[N]` objelerini detect** eder. Diğer alanları (summary, sources) son `parse_x_post_response` ile final pass'te alır.

## Algoritma

```python
class StreamingPostExtractor:
    def feed(chunk: str) -> list[(int, dict)]:
        # 1. Buffer'a chunk ekle
        # 2. `"posts": [` pattern'ini ara (yalnız bir kere)
        # 3. Bulunduğunda scan_pos'tan ileri git, her bir tam {} objesi parse et
        # 4. Yeni post(lar) için (index, dict) döndür
        # 5. `]` ile array kapanırsa daha fazla scan etme
```

**String-aware brace matcher:**

```python
def find_matching_brace(text, start):
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape: escape = False
            elif ch == '\\': escape = True
            elif ch == '"': in_string = False
        else:
            if ch == '"': in_string = True
            elif ch == '{': depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0: return i
    return -1  # buffer yetersiz, sonraki feed'de devam
```

## Edge case'ler (test edildi — 10/10)

| Edge case | Çözüm |
|---|---|
| Tek chunk = tüm response | `feed(full)` → 3 post döner, posts_array_closed=True |
| Karakter-karakter chunking | Her char `feed`'i ile state ilerler; emit timing aynı |
| Chunk ortası post text içinde | `find_matching_brace -1` döner, `scan_pos` korunur, sonraki feed devam |
| Escape edilmiş tırnak `\"` | `escape=True` flag'i string sonunu bilir; brace counter etkilenmez |
| String içinde `}` (örn. "Bracket: `}`") | `in_string=True` iken `}` saymaz |
| Boş posts array `[]` | İlk `]` görüldüğünde `posts_array_closed=True` |
| Bozuk obje (eksik kolon vb.) | `json.loads` fail → o obje skip, sonraki valid emit |
| Posts kapandıktan sonra ekstra feed | scan'i ilk `]`'da durdurur, atılır |

## Ne YAPMAZ

- **Tam JSON parse etmez:** `summary`, `sources`, `summary_doc_*` final `parse_x_post_response` ile çıkar (stream sonu sonrası).
- **Token-level decode:** delta_text raw geçer; frontend isterse raw `chunk` event'inden partial preview yapabilir (`/lib/api.ts` bunu yapmıyor, sadece `post` event'inde structured data gösteriyor).
- **Schema validation:** post objesi dict mi diye bakar ama field-level constraint yapmaz (final parse_x_post_response ile yapılır).

## Kullanım yeri

[apps/api/app/api/app_generate_stream.py:421](../../apps/api/app/api/app_generate_stream.py) — DeepSeek stream loop içinde her delta'da `extractor.feed()` çağrılır; dönen `(index, post_obj)` tuple'ı `event: post` SSE event'i olarak frontend'e yollanır.

## İlişkiler

- **İlgili karar:** [[sse-streaming-default]] (bu parser SSE endpoint'in core mekaniği)
- **İlgili konseptler:** [[speculative-retrieval]], [[planner-cache]] (aynı PR'da geldiler — TTFT < 1s hedefinin üç ayağı)
- **İlgili topics:** [[pipeline-performance-baseline]] (MVP-2.2)
- **İlgili varlıklar:** [[deepseek]] (json_mode response chunk source)

## Açık sorular / TODO

- Token-level `posts[N].text` delta event'i (örn. `event: post_text_delta`) — şu an post bütünüyle emit ediliyor; karakter-karakter flow için frontend `chunk` event'inden partial JSON parse yapabilir. ChatGPT'nin token-by-token UX'i bu kararı yeniden gözden geçirmeyi gerektirebilir.
- Summary/sources için ayrı extractor — şu an stream sonu pass yeterli; eğer summary çok uzun text olursa benzer logic eklenebilir.
- Multi-language response (TR/EN karışık prompt) için unicode escape `\uXXXX` testi — Python `json.loads` zaten doğru handle ediyor; testte explicit case yok.
