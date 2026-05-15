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
  - "GitHub PR #823 #824 #825 #827(#828) #836(#840 revize) #840 #842"
tags: ["rag", "chat", "tool-use", "function-calling", "wikipedia", "mvp-1-8", "faz-2"]
aliases: ["tool-use-architecture", "search-wikipedia-tool"]
---

# LLM Tool-Use Wikipedia

> ⚠️ **Orkestrasyon SUPERSEDED (#845):** "Ön-retrieval (haber chunks) → Aşama 1'de search_wikipedia tool" kısmı [[agentic-generate-orchestration]] ile değişti — artık ön-retrieval YOK; haber arşivi de `search_news` tool'u, LLM ikisini orkestre eder. Bu sayfanın **`search_wikipedia` tool spec'i + #840 non-streaming Aşama 1 + #842 entity/grounding/C1 kuralları GEÇERLİ** (yeni mimaride de aynen kullanılıyor). Sadece "her sorguda haber chunks pre-load" framing'i geçersiz.

> **TL;DR:** Chat'te kaynak yetersizse **LLM kendi kararıyla** `search_wikipedia` tool'unu çağırır (OpenAI-compatible function calling). Confidence-based routing + Wikipedia CTA banner + meta-query resubmit mimarisi (eski #810/#814/#816) **tamamen terk edildi**. #845 sonrası haber arşivi de tool (`search_news`); bkz [[agentic-generate-orchestration]].

## Bağlam — neden eski mimari terk edildi

Faz 2'nin ilk mimarisi (#810 confidence router + #814 Wikipedia CTA + #816 insufficiency banner) production'da defalarca kırıldı:

- "trump kaç yaşında" → bazı haber chunk'ları yüksek RRF skoru aldığı için confidence T_low üstünde kalıyor → Wikipedia CTA tetiklenmiyor → "kaynaklarda yok" cevabı
- CTA tetiklense bile kullanıcı tıklayınca yeni mesaj `meta_query`'e düşüyor → "konuşmamızda bilgi yok" saçma cevabı
- Pattern-matching ile LLM cevabını analiz etme denemesi (#819) anti-pattern — kullanıcı reddetti: "LLM'den gelecek yanıta güvenerek işlem yapamazsın, her zaman farklı cümleyle dönebilir"

Kök içgörü (kullanıcı): *"LLM eğer kullanıcı sorgusunu cevaplayacak bir kaynağa sahip değilse tool kullanma yeteneğiyle geri dönüp wikipedia sürecini tetiklemeli, akışı bozmadan. Bu mimari aslında çok basit."*

## Karar

LLM'e `search_wikipedia` tool'u verilir; **karar verici LLM, planner veya confidence skoru değil.**

### 2-aşamalı akış — non-streaming Aşama 1 (`app_chat_stream.py`, #840 güncel)

```
Step 1.5 (multi-turn): condense_followup_query → effective_query
                        ([[conversational-query-rewriting]])
Aşama 1 (NON-streaming): generate_text(messages=[sys+haber chunks],
                          tools=[search_wikipedia], tool_choice="auto")
   → yapısal decision.tool_calls + decision_text (content YIELD EDİLMEZ)
   ├─ tool YOK → decision_text, _simulate_stream ile yield
   │    (4-kelime grup + 18ms; EKSTRA LLM CALL YOK — text zaten üretildi)
   └─ tool_calls dolu → LLM Wikipedia istedi:
        ├─ execute_search_wikipedia(args) → Wikipedia+Wikidata sonucu
        ├─ messages += [assistant(tool_calls), tool(result)]
        └─ Aşama 2 (STREAMING, TOOLSUZ): generate_text_stream →
             gerçek token streaming + [W1][W2] citation
```

> **#840 — DeepSeek DSML token bug (kritik):** #836'nın "Aşama 1
> streaming" tasarımı production'da kırıldı. DeepSeek
> `generate_text_stream(tools=...)` tool çağıracağında yapısal
> `delta.tool_calls` DÖNMEZ — `<｜DSML｜tool_calls>` özel token'ını
> **content içinde ham XML** olarak yayınlar. Sonuç: kullanıcı ham DSML
> görüyor + "uzun uzun yazıp bir anda kısa yanıta dönme" (content stream
> sonra tool branch'ine atlıyor). Düzeltme: Aşama 1 tekrar **non-streaming
> `generate_text(tools=...)`** → yapısal `decision.tool_calls` doğru parse
> (DeepSeek non-streaming function calling ÇALIŞIR, #825'te doğrulandı).
> Aşama 1 content **yield edilmez** (ham DSML kullanıcıya gitmez). Tool
> varsa Aşama 2 = `generate_text_stream` **TOOLSUZ** (tool param yok → DSML
> token yok → gerçek token streaming sağlam). Tool yoksa `decision_text`
> `_simulate_stream` ile (4-kelime grup + 18ms, ekstra LLM call YOK).
> Ana flow + `_stream_meta_query_answer` ikisine de uygulandı. **Mid-stream
> tool execution DEĞİL** (kullanıcı #823'te reddetti). `generate_text_stream`
> tool param'ları (#836) API'de kalıyor (ileride OpenAI-uyumlu provider
> için; chat flow kullanmıyor).

> **#834 — entity-relevance:** TOOL_USE_INSTRUCTION'a net karar kuralı:
> "Kaynaklar sorudaki ENTITY hakkında değilse — aynı kelime ('ilk
> bölüm') başka bağlamda geçse bile — keyword match cevap sayılmaz,
> sentez yapma, search_wikipedia çağır." Çöp retrieval'ın LLM'i
> yanıltmasını engeller.

> **#835 — tool query bağlamı:** `gen_user_msg` "Soru:" =
> `effective_query` (condense çıktısı), HAM mesaj değil. Yoksa LLM
> tool'u bağlamsız çağırıp Wikipedia çöpü getiriyordu.

> **#842 — entity-only tool query + C1 grounding backstop + meta-leak:**
> Üç kusur (Stargate SG-1 kullanıcı testi). (1) **Yanlış sayfa:** LLM
> `search_wikipedia` query'sine "Stargate SG-1 4. sezon" (İngilizce ad +
> niteleyici) gönderiyordu → TR Wikipedia full-text "200 (Yıldız Geçidi
> SG-1)/Paul Mullie/Atlantis" döndürüyor; temiz Türkçe entity "Yıldız
> Geçidi SG-1" → #1 doğru ana sayfa (canlı API testi). Fix: tool `query`
> param + TOOL_USE_INSTRUCTION → SADECE kanonik Türkçe madde adı, soru/
> sezon/bölüm/niteleyici kelimeleri çıkar (anti-pattern #3 güçlendirme).
> (2) **C1 fabrication (kritik):** Sorulan spesifik detay ("S4E1 adı")
> dönen REST özetinde HİÇ yoktu (ana sayfa = sadece lead; Wikidata
> P-prop'larında da yok) → LLM cevabı kendi belleğinden üretip **sahte
> [W1]** ekledi. Fix: grounding kuralı — her olgu dönen araç metninde
> LİTERAL olmalı; yoksa scope-aware "özette yer almıyor" de, uydurma+
> sahte cite YOK. Output pattern-match DEĞİL (anti-pattern #2; #819
> reddi korunur) — sadece input-side prompt. (3) **Meta-leak:** Aşama 2
> "kaynaklarda yok, bu yüzden Wikipedia'ya başvurdum" iç sürecini
> yazıyordu → cevap biçimi kuralı: iç mekanizma anlatılmaz, sadece
> cevap + citation.

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

- `apps/api/app/api/app_chat_stream.py` (Step 1.5 condense + 2-aşama: non-streaming Aşama 1 + toolsuz Aşama 2 stream + `_simulate_stream` + meta-query handler)
- `apps/api/app/core/chat_tools.py` (SEARCH_WIKIPEDIA_TOOL + executor)
- `apps/api/app/providers/deepseek.py` (function calling — `generate_text(tools=)` yapısal tool_calls; `generate_text_stream` tool param #836 API'de kalır ama chat flow toolsuz çağırır)
- `apps/api/app/prompts/chat_answer.py` (TOOL_USE_INSTRUCTION — entity-relevance #834)
- `apps/api/app/prompts/query_rewrite.py` (#833 condense)
- GitHub PR #823 (tool-use) #824 (prompt fix) #825 (stream serialize + wiki relevance) #827/#828 (fast-path revert + Wikidata) #831 (meta-query tool) #833 (condense) #834 (entity-relevance) #835 (effective_query) #836 (tool-aware streaming — #840 ile revize) #840 (DeepSeek DSML token bug → non-streaming Aşama 1) #842 (entity-only tool query + C1 grounding backstop + meta-leak fix)
