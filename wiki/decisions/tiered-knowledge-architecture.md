---
type: decision
title: "Tiered Knowledge Architecture — Layer 1 / 2 / 3 katmanlama"
slug: "tiered-knowledge-architecture"
category: "rag"
status: "live"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "apps/api/app/api/app_chat_stream.py§313-490"
  - "apps/api/app/core/retrieval_confidence.py"
  - "GitHub Issue #808 / PR #810 + #812 + #814 + #816"
tags: ["rag", "chat", "architecture", "perplexity", "mvp-1-8", "faz-2"]
aliases: ["3-layer-architecture", "tiered-retrieval"]
---

# Tiered Knowledge Architecture

> **TL;DR:** Chat sohbet'i 3 bilgi katmanına ayrılır — Layer 1 (haber arşivi, mevcut moat), Layer 2 (Wikipedia + Wikidata, opsiyonel fallback), Layer 3 (conversation memory). Confidence Router (5-signal score) hangi katmanın tetikleneceğini belirler. LLM kendi bilgi haznesinden ASLA cevap yok (C1 locked).

## Bağlam — sorun

Faz 1 (chat-only migration, #800-#807) production'a alındı. Chat şu anda sadece **Layer 1** (news intelligence — agenda card + chunks-first retrieval). Ama kullanıcı sohbeti "general assistant" gibi kullanmaya başladı (Trump-Çin-Putin sohbetinde fark edildi). Üç tür sorgu sistemi kırıyor:

1. **Genel bilgi sorguları** — "Çin nüfusu?", "NATO ne zaman kuruldu?" → haberlerde arayıp alakasız kaynak getiriyor
2. **Meta sorgular** — "Az önce ne dedin?" → yeni retrieval başlatıyor, oysa konuşma context'inden cevaplanmalı
3. **Kaynak yetersizliği** — "Türkiye savunma sanayi 2026 ihracat" → kaynak yok ama yine de cevap üretiyor (halüsinasyon)

## Karar

3 katmanlı bilgi mimarisi:

```
User Query
   ↓
[Layer 3] Conversation Resolver  (mevcut — Faz 1)
   ↓  conversations.summary + son 6 mesaj prompt'a inject
Query Planner (intent + query_class)
   ↓
Confidence Router (5-signal score)  ← retrieval_confidence.py
   ├──> Layer 1: News Retrieval    (chunks-first-retrieval, agenda)
   │     score >= T_high → STRICT (Wikipedia leak yok)
   │     T_low <= score < T_high → hybrid (cevap + insufficiency CTA)
   ├──> Layer 2: Wikipedia/Wikidata (Faz 2 yeni, providers/wikipedia.py)
   │     kullanıcı CTA onayı sonrası
   └──> Scope-aware refusal
         (Layer 1 boş + Wikipedia reddedildi)
```

**Katmanlar:**

- **Layer 1 — Realtime News** (mevcut, Faz 1): event-based agenda, trusted sources, freshness-weighted retrieval. Nodrat moat. Tüm news_query sorgular buradan cevaplanır.
- **Layer 2 — General Knowledge** (yeni, Faz 2 #811): Wikipedia REST + Wikidata SPARQL. CC BY-SA 4.0 lisansı, 25-kelime quote cap (FSEK), Redis 24h cache, $0 cost.
- **Layer 3 — Conversation Memory** (mevcut, Faz 1): `conversations.summary` (auto-generated) + son N mesaj prompt'a injection.

## Routing logic

`apps/api/app/api/app_chat_stream.py`:

| Path | Trigger | Davranış |
|---|---|---|
| Meta-query bypass | `query_class='meta_query'` | Step 2.5 — retrieval atlanır, conversation context'ten cevap (#815 2C) |
| Layer 1 STRICT | `query_class='news_query'` VEYA `score >= T_high` | Mevcut akış (haber arşivi); Wikipedia ASLA tetiklenmez (C2) |
| Hybrid | `T_low <= score < T_high` AND `query_class != news_query` | Cevap üret + `insufficiency_signal` event (Wikipedia teklifi banner) |
| Wikipedia CTA | `score < T_low` AND `query_class != news_query` | Stream durur, `requires_user_consent` event, stub message persist |
| Scope-aware refusal | Wikipedia kapalı VEYA reddedildi | Kısa "yardım edemem, başka bir konu?" |

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

- Confidence formula: [[confidence-based-routing]]
- Wikipedia knowledge layer: [[wikipedia-fallback-controlled]]
- News leak engelleme: [[news-first-strict-contamination-guard]]
- Mevcut retrieval: [[chunks-first-retrieval]] (Layer 1 omurgası)
- Meta-query: [[query-class-classification]]

## Kaynaklar

- [Plan dokümanı](/Users/selmanay/.claude/plans/nerdi-in-ekilde-faz-2-unified-nebula.md)
- `apps/api/app/api/app_chat_stream.py:313-490` (routing logic)
- `apps/api/app/core/retrieval_confidence.py` (5-signal compute)
- `apps/api/app/providers/wikipedia.py` (Layer 2 provider)
- GitHub Issue #808 (umbrella) + PR'lar #810 (2A) #812 (2E) #814 (2B) #816 (2C+2D+2F)
