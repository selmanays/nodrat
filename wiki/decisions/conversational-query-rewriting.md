---
type: decision
title: "Conversational query rewriting — follow-up → standalone (condense step)"
slug: "conversational-query-rewriting"
category: "rag"
status: "live"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "apps/api/app/prompts/query_rewrite.py"
  - "apps/api/app/api/app_chat_stream.py (Step 1.5)"
  - "GitHub PR #833 #835"
tags: ["rag", "chat", "conversational", "query-rewrite", "follow-up", "mvp-1-8", "faz-2"]
aliases: ["condense-question", "standalone-query", "follow-up-rewrite"]
---

# Conversational query rewriting

> **TL;DR:** Multi-turn'de planner'dan ÖNCE izole bir hafif LLM call follow-up mesajı standalone arama sorgusuna çevirir ("ilk bölümün adı neydi" → "Stargate SG-1 ilk bölüm adı"). Bu standalone query planner + retrieval + tool query'ye tutarlı akar. Perplexity/LangChain ConversationalRetrievalChain "condense question" standardı.

## Bağlam — neden gerekli

Follow-up sorular ("ilk bölümün adı neydi", "daha detaylı açıkla", "kaç yıl önce") önceki konuşmaya atıf içerir. Bağlam retrieval'a yansımazsa felaket: production'da "stargate sg-1 ne zaman yayınlandı" → Wikipedia (doğru); follow-up "ilk bölümün adı neydi" → "ilk bölüm" Merdan Yanardağ casusluk davasında / "Daha 17" Türk dizisinde geçtiği için o haberler geldi. "daha detaylı açıkla" → CHP yolsuzluk haberi.

### Başarısız ara çözümler (anti-pattern kayıtları)

| PR | Yaklaşım | Neden yetmedi |
|---|---|---|
| #829 | Follow-up context'i gen_user_msg'e ekle | Cevap-üretim aşamasına context — retrieval hâlâ HAM mesajla |
| #831 | meta-query handler'a tool | Sadece meta_query path; news/general path ham |
| #832 | plan_query user_request'ine context+talimat göm | Planner SYSTEM_PROMPT preserve-first kuralı ad-hoc talimatı EZDİ — topic_query'yi son satırdan üretti, bağlamı ignore etti |

Kök içgörü: planner'ın sabit prompt'una ad-hoc talimat gömmek çalışmaz (system prompt baskın). Standalone query üretimi **ayrı, izole bir adım** olmalı.

## Karar

`apps/api/app/api/app_chat_stream.py` **Step 1.5** — planner'dan önce:

```
_recent_conversation_context VARSA (multi-turn):
  condense_followup_query(provider, history, payload.content)
    → effective_query (standalone)
plan_query(user_request=effective_query)
retrieval query_text = topic (planner'ın effective_query'den ürettiği)
gen_user_msg "Soru:" = effective_query   (#835 — tool query bağlamlı)
```

- `apps/api/app/prompts/query_rewrite.py` (YENİ): `REWRITE_SYSTEM_PROMPT` + `condense_followup_query` — chat-capable provider, `max_tokens=80`, `temp=0.3`, ~300-500ms.
- **is_related embedding'ine GÜVENİLMEZ.** Generic follow-up ("daha detaylı açıkla") önceki mesajla semantic similar değil → embedding kaçırır. Bunun yerine: conversation context VARSA (multi-turn) her zaman condense.
- **#835:** effective_query sadece planner+retrieval'a değil, `gen_user_msg`'deki "Soru:" satırına da gider. Yoksa LLM `search_wikipedia` tool'unu HAM mesajla çağırıp Wikipedia çöpü getiriyordu ("Rolls-Royce Nene", "Viyolonsel").

## Why — neden izole adım (planner'a gömmek değil)

- Planner SYSTEM_PROMPT generic (agenda generation dahil her yerde kullanılır); follow-up kuralı eklemek riskli + preserve-first ile çelişir.
- İzole condense step planner'a dokunmaz; standalone query'de planner'ın preserve-first kuralı zaten DOĞRU çalışır (çatışma yok).
- Evergreen: spesifik pattern yok, LLM standalone üretir. İlk mesajda context boş → ekstra call yok.

## Trade-off (bilinçli)

Multi-turn'de ~0.5s ek LLM call. Follow-up doğruluğu için kritik (yoksa tamamen alakasız cevap). Kullanıcı ilkesi: doğruluk > latency.

## İlişkiler

- Üst mimari: [[llm-tool-use-wikipedia]] (tool query effective_query ile)
- Tiered mimari: [[tiered-knowledge-architecture]]
- Knowledge source: [[wikipedia-wikidata-knowledge-source]]
- Evrim/anti-pattern: [[chat-knowledge-evolution]]

## Kaynaklar

- `apps/api/app/prompts/query_rewrite.py` (REWRITE_SYSTEM_PROMPT + condense_followup_query)
- `apps/api/app/api/app_chat_stream.py` (Step 1.5 + effective_query akışı)
- `apps/api/app/core/chat_tools.py` (tool query — entity-relevant)
- GitHub PR #833 (condense step) #835 (effective_query → gen_user_msg)
