---
type: concept
title: "Style Analyzer prompt v1.0"
slug: "style-analyzer-prompt"
category: "technique"
status: "live"
created: "2026-05-09"
updated: "2026-05-09"
sources:
  - "docs/engineering/prompt-contracts.md§5.1"
  - "docs/product/prd.md§5.3"
tags: [faz-5, llm, json-mode, prompt-contract]
aliases: ["stil analyzer", "Faz 5 prompt"]
---

# Style Analyzer prompt v1.0

> **TL;DR:** 3-50 örnek metinden ortak stil özelliklerini 7 alanlı JSON şemasıyla çıkaran tek-seferlik DeepSeek V3 prompt'u. Pro+ tier'da `style_profiles.rules_json` doldurmak için kullanılır. Sürüm `1.0.0`, prompt cache hit hedefi yok (kullanıcı başına unique).

## Tanım

`apps/api/app/prompts/style_analyzer.py` içinde tek system prompt + helper:

- `SYSTEM_PROMPT` — JSON şema tanımlı, 8 zorunlu kural
- `render_user_payload(samples)` — `Örnek N: …` formatında listele, sample başına 4k karakter trim
- `parse_response(raw)` — markdown fence temizle + JSON parse + type coercion + zorunlu key kontrolü

## Neden Nodrat'ta var

- PRD §5: kullanıcı kendi yazı stilini öğretebilmeli, sistem nötr içerik üretmek yerine bu kuralları gözetmeli
- `content_generator` Rule 11 zaten `style_profile verildiyse uy` diyor; analyzer bu rules_json'u beslemenin tek yolu
- Faz 6 paywall'ında Pro tier'a fonksiyonel özellik gerek (`features.style_profiles=true`)

## Schema

```json
{
  "style_name": "string (2-6 kelime)",
  "style_summary": "string (1-2 cümle)",
  "sentence_length": "short | medium | long",
  "tone": ["sade", "eleştirel", "..."],
  "rhetorical_patterns": ["Önce iddia, sonra veri", "..."],
  "avoid": ["aşırı slogan", "..."],
  "sample_transforms": [{ "generic": "...", "styled": "..." }]
}
```

Yetersiz örnek edge-case'i için BELIRSIZ output:

```json
{ "style_name": "BELIRSIZ", "style_summary": "Yetersiz örnek", ... }
```

## Sözleşmeler / kurallar

| # | Kural |
|---|---|
| 1 | Stil özelliklerini ortak gözlemden çıkar; tek örneğe bağlı kalma |
| 2 | tone Türkçe ve özlü; "ilginç/kaliteli" gibi genel laflar yasak |
| 3 | rhetorical_patterns eylem cümlesi |
| 4 | avoid başkalarına sürtmesin |
| 5 | 15+ kelimelik birebir alıntı yapma (FSEK 35) |
| 6 | Gerçek kişi adı/PII üretme (kullanıcı örneklerinden sızabilir) |
| 7 | JSON dışı çıktı yok (markdown/açıklama yasak) |
| 8 | sample_transforms generic = nötr, styled = bu stilde, 1 cümle max |

## Parametreler

| Parametre | Değer |
|---|---|
| Provider | DeepSeek V3 (`registry.route_for_tier(operation="chat", tier="free")`) |
| max_tokens | 2000 |
| temperature | 0.2 (deterministik tercih) |
| json_mode | `True` |
| Retry (Celery) | autoretry_for=Exception, max_retries=2, backoff up to 5 min |
| MIN_SAMPLES (analyze trigger) | 3 |
| MAX_SAMPLES (prompt limit) | 50 |
| MAX_TOTAL_CHARS | 80 000 (≈ 25k token, güvenli) |

## İlişkiler

- Tüketen: [[style-profile-system]]
- Provider: [[deepseek|DeepSeek (default LLM)]]
- Bağlı kural: [[twenty-five-word-quote-cap|25-kelime FSEK direct quote cap]]
- Bağlı kural: [[pii-redaction-mandatory]]

## Açık sorular / TODO

- BELIRSIZ output handling: parse başarılı ama style_name=="BELIRSIZ" durumunda profil status='ready' kalıyor; UI bunu farklı renkte göstermeli mi? Şu an ready badge görünür.
- Eval fixture: prompt output kalitesi için 5-10 örnek style sample'lı snapshot test eklenmedi (test_style_analyzer_prompt.py sadece structural validation).

## Kaynaklar

- [docs/engineering/prompt-contracts.md §5.1](../../docs/engineering/prompt-contracts.md)
- [docs/product/prd.md §5.3](../../docs/product/prd.md)
- `apps/api/app/prompts/style_analyzer.py` (PROMPT_VERSION = "1.0.0")
- `apps/api/tests/unit/test_style_analyzer_prompt.py` (render + parse + type coercion tests)
