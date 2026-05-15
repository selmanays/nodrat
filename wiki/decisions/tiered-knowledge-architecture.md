---
type: decision
title: "Tiered Knowledge Architecture — Layer 1 / 2 / 3 katmanlama"
slug: "tiered-knowledge-architecture"
category: "rag"
status: "live"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "apps/api/app/api/app_chat_stream.py"
  - "apps/api/app/core/chat_tools.py"
  - "GitHub Issue #808 / PR #810→#828"
tags: ["rag", "chat", "architecture", "perplexity", "mvp-1-8", "faz-2"]
aliases: ["3-layer-architecture", "tiered-retrieval"]
---

# Tiered Knowledge Architecture

> **TL;DR:** Chat 3 bilgi katmanına ayrılır — Layer 1 (haber arşivi, moat), Layer 2 (Wikipedia + Wikidata), Layer 3 (conversation memory). **Katmanlar arası geçiş LLM tool-use ile** ([[llm-tool-use-wikipedia]]) — LLM haber yetersizse `search_wikipedia` çağırır. Confidence-based routing (ilk tasarım #810) **terk edildi**, artık sadece telemetri. LLM kendi bilgi haznesinden ASLA cevap yok (C1 locked).
>
> ⚠️ **Mimari evrim:** confidence router + CTA + banner kırıldı → tool-use (#823→#828) → **#845 agentic RAG-as-tool**. Artık ön-retrieval YOK; Layer 1 (haber) de bir tool (`search_news`), LLM `search_news`+`search_wikipedia`'yı orkestre eder. Routing/CTA/banner + "her sorguda Layer 1 retrieval" tarihsel — güncel akış: [[agentic-generate-orchestration]].

## Bağlam — sorun

Faz 1 (chat-only migration, #800-#807) production'a alındı. Chat şu anda sadece **Layer 1** (news intelligence — agenda card + chunks-first retrieval). Ama kullanıcı sohbeti "general assistant" gibi kullanmaya başladı (Trump-Çin-Putin sohbetinde fark edildi). Üç tür sorgu sistemi kırıyor:

1. **Genel bilgi sorguları** — "Çin nüfusu?", "NATO ne zaman kuruldu?" → haberlerde arayıp alakasız kaynak getiriyor
2. **Meta sorgular** — "Az önce ne dedin?" → yeni retrieval başlatıyor, oysa konuşma context'inden cevaplanmalı
3. **Kaynak yetersizliği** — "Türkiye savunma sanayi 2026 ihracat" → kaynak yok ama yine de cevap üretiyor (halüsinasyon)

## Karar

3 katmanlı bilgi mimarisi. **Katmanlar arası geçiş LLM tool-use ile** (güncel — [[llm-tool-use-wikipedia]]):

```
User Query
   ↓
[Layer 3] Conversation Resolver  (Faz 1)
   ↓  conversations.summary + son 6 mesaj prompt'a inject
Query Planner (intent + query_class)
   ↓
query_class routing:
   ├─ meta_query        → Layer 3 (conversation context, retrieval atla)
   ├─ news_query        → Layer 1 STRICT (haber, tool YOK — C2)
   └─ general_kn./mixed → Layer 1 retrieval + LLM tool-use:
        Aşama 1: LLM haber chunks + search_wikipedia tool görür
          ├─ haber yeterli → Layer 1 cevap
          └─ haber yetersiz → search_wikipedia çağırır → Layer 2
        Aşama 2: Wikipedia+Wikidata sonucuyla [W1] citation cevap
```

**Katmanlar:**

- **Layer 1 — Realtime News** (Faz 1): event-based agenda, trusted sources, freshness-weighted retrieval. Nodrat moat. Tüm news_query buradan.
- **Layer 2 — General Knowledge** (Faz 2): Wikipedia REST (`list=search`) + Wikidata SPARQL kombine ([[wikipedia-wikidata-knowledge-source]]). CC BY-SA 4.0 + CC0, 25-kelime cap (FSEK), Redis 24h cache, $0.
- **Layer 3 — Conversation Memory** (Faz 1): `conversations.summary` + son N mesaj prompt'a injection.

## Routing logic (GÜNCEL — tool-use)

`apps/api/app/api/app_chat_stream.py` — detay [[llm-tool-use-wikipedia]]:

| query_class | Davranış | Tool |
|---|---|---|
| `meta_query` | Step 2.5 — retrieval atlanır, conversation context'ten cevap | yok |
| `news_query` | Haber arşivi; Wikipedia ASLA tetiklenmez (C2 STRICT) | yok |
| `general_knowledge` / `mixed` | Haber retrieval + LLM `search_wikipedia` tool kararı | search_wikipedia |

> **Tarihsel (terk edildi):** İlk tasarım confidence skoruna göre STRICT/hybrid/CTA/refusal routing yapıyordu (T_high 0.70 / T_low 0.40). Bu mimari production'da kırıldı (planner+RRF "konu geçiyor" der ama "cevap var" demez); LLM tool-use ile değiştirildi. confidence skoru artık sadece telemetri ([[confidence-based-routing]]).

## Why

- **Brand integrity:** Nodrat = "news intelligence engine". LLM kendi bilgi haznesinden cevap sistem güvenini öldürür. Sadece kaynaklı veya cevapsız.
- **News-first STRICT (C2):** "Trump bugün ne dedi?" Wikipedia'ya düşmemeli — contamination. `query_class='news_query'` gate'i bu invariant'ı garanti eder.
- **Controlled Wikipedia (C3):** Wikipedia PRIMARY değil — fallback. Kullanıcı CTA onayı zorunlu, aksi halde generic-assistant'a kayar.
- **Tier-based UX:** Kullanıcı "akıllı asistan" hisseder (mod seçmiyor); confidence-based auto-routing.

## Alternatifler

| Alternatif | Reddetme nedeni |
|---|---|
| **LLM kendi bilgi haznesi fallback** | C1 — halüsinasyon riski yüksek, brand integrity kaybı |
| **Wikipedia PRIMARY** | C3 — brand contamination ("generic assistant"a kayar) |
| **"Source mode" UI butonları** | C4 — mod seçmek UX'i bozar, chat akıcılığını öldürür |
| **Britannica** | C5 — lisans ücretli, Wikipedia + Wikidata %95 kapsar |
| **Mod tabanlı routing (manuel)** | UX karmaşası, auto-routing daha zarif |

## İlişkiler

- **Güncel akış:** [[llm-tool-use-wikipedia]] (tool-use — confidence routing'in yerine)
- Follow-up bağlam (Step 1.5): [[conversational-query-rewriting]]
- Layer 2 kaynak: [[wikipedia-wikidata-knowledge-source]]
- Terk edilen routing: [[confidence-based-routing]] (telemetri-only)
- Terk edilen CTA: [[wikipedia-fallback-controlled]] (superseded)
- News leak gating: [[news-first-strict-contamination-guard]]
- Layer 1 omurgası: [[chunks-first-retrieval]]
- Sorgu sınıflandırma: [[query-class-classification]]
- Karar/vazgeçiş zinciri: [[chat-knowledge-evolution]]

## Kaynaklar

- `apps/api/app/api/app_chat_stream.py` (query_class routing + tool-loop)
- `apps/api/app/core/chat_tools.py` (search_wikipedia)
- `apps/api/app/providers/wikipedia.py` (Layer 2 provider)
- GitHub Issue #808 (umbrella) + PR'lar #810 #812 #814 #816 (ilk tasarım) → #823 #824 #825 #827/#828 (tool-use evrim)
