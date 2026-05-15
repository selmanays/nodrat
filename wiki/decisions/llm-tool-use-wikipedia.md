---
type: decision
title: "LLM Tool-Use Wikipedia — confidence routing/CTA terk edildi"
slug: "llm-tool-use-wikipedia"
category: "rag"
status: "live"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "apps/api/app/api/app_chat_stream.py"
  - "apps/api/app/core/chat_tools.py"
  - "apps/api/app/providers/deepseek.py§125-368 (function calling)"
  - "apps/api/app/prompts/chat_answer.py (TOOL_USE_INSTRUCTION)"
  - "GitHub PR #823 #824 #825 #827(#828)"
tags: ["rag", "chat", "tool-use", "function-calling", "wikipedia", "mvp-1-8", "faz-2"]
aliases: ["tool-use-architecture", "search-wikipedia-tool"]
---

# LLM Tool-Use Wikipedia

> **TL;DR:** Chat'te haber kaynakları kullanıcının sorusunu cevaplamıyorsa **LLM kendi kararıyla** `search_wikipedia` tool'unu çağırır (OpenAI-compatible function calling). Confidence-based routing + Wikipedia CTA banner + meta-query resubmit mimarisi (eski #810/#814/#816) **tamamen terk edildi** — kullanıcı "çok kompleks bir noktaya getirdin, mimari aslında çok basit" geri bildirimi sonrası. Tek akış, kullanıcı müdahalesi yok.

## Bağlam — neden eski mimari terk edildi

Faz 2'nin ilk mimarisi (#810 confidence router + #814 Wikipedia CTA + #816 insufficiency banner) production'da defalarca kırıldı:

- "trump kaç yaşında" → bazı haber chunk'ları yüksek RRF skoru aldığı için confidence T_low üstünde kalıyor → Wikipedia CTA tetiklenmiyor → "kaynaklarda yok" cevabı
- CTA tetiklense bile kullanıcı tıklayınca yeni mesaj `meta_query`'e düşüyor → "konuşmamızda bilgi yok" saçma cevabı
- Pattern-matching ile LLM cevabını analiz etme denemesi (#819) anti-pattern — kullanıcı reddetti: "LLM'den gelecek yanıta güvenerek işlem yapamazsın, her zaman farklı cümleyle dönebilir"

Kök içgörü (kullanıcı): *"LLM eğer kullanıcı sorgusunu cevaplayacak bir kaynağa sahip değilse tool kullanma yeteneğiyle geri dönüp wikipedia sürecini tetiklemeli, akışı bozmadan. Bu mimari aslında çok basit."*

## Karar

LLM'e `search_wikipedia` tool'u verilir; **karar verici LLM, planner veya confidence skoru değil.**

### 2-aşamalı akış — tool-aware STREAMING (`app_chat_stream.py`, #836 güncel)

```
Step 1.5 (multi-turn): condense_followup_query → effective_query
                        ([[conversational-query-rewriting]])
Aşama 1 (STREAMING): generate_text_stream(messages=[sys+haber chunks],
                      tools=[search_wikipedia], tool_choice="auto")
   ├─ content delta gelir → ANINDA yield (gerçek token streaming)
   │    → tool yok, stream edilen text = final cevap
   └─ content boş + final chunk tool_calls dolu → LLM tool istedi:
        ├─ execute_search_wikipedia(args) → Wikipedia+Wikidata sonucu
        ├─ messages += [assistant(tool_calls), tool(result)]
        └─ Aşama 2 (STREAMING): final cevap [W1][W2] citation ile
```

> **#836 — gerçek streaming:** Eski tasarım Aşama 1'i non-streaming
> `generate_text` yapıyordu → tool çağrılmazsa cevap tek parça geliyordu
> (streaming UX kaybı). Artık `generate_text_stream(tools=...)`: content
> delta anında yield (gerçek token streaming), `StreamChunk.tool_calls`
> final chunk'ta toplanır. DeepSeek function calling: tool çağıracaksa
> content boş gelir → content akmaya başladıysa model "text üretiyorum"
> kararı vermiştir. **Mid-stream tool execution DEĞİL** (kullanıcı bunu
> #823'te reddetti) — stream biter, sonra tool kontrol.

> **#834 — entity-relevance:** TOOL_USE_INSTRUCTION'a net karar kuralı:
> "Kaynaklar sorudaki ENTITY hakkında değilse — aynı kelime ('ilk
> bölüm') başka bağlamda geçse bile — keyword match cevap sayılmaz,
> sentez yapma, search_wikipedia çağır." Çöp retrieval'ın LLM'i
> yanıltmasını engeller.

> **#835 — tool query bağlamı:** `gen_user_msg` "Soru:" =
> `effective_query` (condense çıktısı), HAM mesaj değil. Yoksa LLM
> tool'u bağlamsız çağırıp Wikipedia çöpü getiriyordu.

### News-first STRICT (C2) — tool-level gating

`query_class == 'news_query'` ise tool LLM'e **hiç verilmez** (`offer_tools = wikipedia_enabled and query_class != "news_query"`). "Trump bugün ne dedi?" haber kaynaklarından cevaplanır, Wikipedia'ya düşmez. Brand contamination koruması artık query_class hard-gate routing'i değil, **tool sunum kontrolü**.

### Prompt çelişkisi fix (#824 — kritik)

`SYSTEM_PROMPT_CHAT_ANSWER` "Wikipedia KULLANMA, kaynakta yoksa 'yok' de" diyor — bu tool ile çelişiyordu (LLM tool'u çağırmıyordu). `offer_tools=True` iken sistem prompt'a `TOOL_USE_INSTRUCTION` eklenir: "kaynakta yoksa 'yok' DEME, search_wikipedia çağır". Halüsinasyon koruması korunur (LLM sadece kaynak/tool sonucu kullanır, kendi belleğinden değil — C1).

## Routing tablosu (güncel)

| query_class | Akış | LLM call | Retrieval | Tool |
|---|---|---|---|---|
| `meta_query` | Conversation context (Step 2.5) | 1 | yok | yok |
| `news_query` | Haber retrieval, tool YOK (C2 STRICT) | 1-2 | var | yok |
| `general_knowledge` / `mixed` | Haber retrieval + tool-use | 1-2 | var | search_wikipedia |

> Haber retrieval `general_knowledge`'ta da yapılır — LLM'in "haberde mi Wikipedia'da mı?" kararını **kaynakları görerek** vermesi için (güvenlik ağı, planner accuracy'sine bağımlı değil). Bkz "Vazgeçilen: fast-path".

## Provider değişiklikleri

`base.py`: `ToolCall` dataclass + `Message.tool_calls/tool_call_id` + `GenerationResult.tool_calls` + `generate_text(tools, tool_choice)`.
`deepseek.py`: OpenAI-compatible function calling — tool serialize (hem `generate_text` hem `generate_text_stream`, #825) + `tool_calls` response parse + multi-turn tool message.

## Vazgeçilen yaklaşımlar (anti-pattern kayıtları)

| Yaklaşım | PR | Neden reddedildi |
|---|---|---|
| Confidence-based routing (T_high/T_low → STRICT/hybrid/CTA) | #810 | Planner+RRF skoru "konu geçiyor mu" der, "cevap var mı" demez — yanlış routing |
| Wikipedia CTA + consent card | #814 | Kullanıcı müdahalesi akışı bozuyor; meta_query resubmit saçmalığı |
| Insufficiency banner (hybrid path) | #816 | Aynı CTA problemi; karmaşık UX |
| Post-gen refusal pattern matching | #819 | LLM çıktısı pattern'a güvenmek brittle — kullanıcı reddetti |
| general_knowledge fast-path (retrieval skip) | #826 | Planner topic_query'sini Wikipedia'ya gönderiyordu → soru kelimeleri relevance'ı kirletti ("stargate atlantis kaç sezondu" → "Ronon Dex" sayfası). #828 ile REVERT. Tool-use path'te LLM temiz entity query üretir. **Doğruluk > latency** |

## Trade-off (bilinçli)

`general_knowledge` sorgularında ~2.2s planner + ~7.4s retrieval + 2 LLM call ≈ 10-12s. Latency yüksek ama doğru + planner-bağımsız. Fast-path bunu kesecekti ama Wikipedia query kalitesini bozdu. Latency optimizasyonu gelecekte fast-path hatası tekrarlanmadan ele alınmalı (Aşama 1'in ürettiği temiz entity query'yi kullanarak).

## İlişkiler

- Follow-up bağlam: [[conversational-query-rewriting]] (Step 1.5 condense)
- Wikipedia + Wikidata kaynak: [[wikipedia-wikidata-knowledge-source]]
- Üst mimari: [[tiered-knowledge-architecture]]
- Terk edilen routing: [[confidence-based-routing]] (artık telemetri-only)
- Terk edilen CTA: [[wikipedia-fallback-controlled]] (superseded)
- News leak gating: [[news-first-strict-contamination-guard]]
- Sorgu sınıflandırma: [[query-class-classification]] (routing değil, tool gating + telemetri)
- Karar/vazgeçiş zinciri: [[chat-knowledge-evolution]]
- Provider: [[wikipedia-provider]]

## Kaynaklar

- `apps/api/app/api/app_chat_stream.py` (Step 1.5 condense + 2-aşama tool-aware streaming + meta-query handler)
- `apps/api/app/core/chat_tools.py` (SEARCH_WIKIPEDIA_TOOL + executor)
- `apps/api/app/providers/deepseek.py` (function calling — generate_text + generate_text_stream tool-aware #836)
- `apps/api/app/prompts/chat_answer.py` (TOOL_USE_INSTRUCTION — entity-relevance #834)
- `apps/api/app/prompts/query_rewrite.py` (#833 condense)
- GitHub PR #823 (tool-use) #824 (prompt fix) #825 (stream serialize + wiki relevance) #827/#828 (fast-path revert + Wikidata) #831 (meta-query tool) #833 (condense) #834 (entity-relevance) #835 (effective_query) #836 (tool-aware streaming)
