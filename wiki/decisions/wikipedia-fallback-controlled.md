---
type: decision
title: "Wikipedia fallback — CONTROLLED, kullanıcı CTA onayıyla"
slug: "wikipedia-fallback-controlled"
category: "rag"
status: "live"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "apps/api/app/providers/wikipedia.py"
  - "apps/api/app/api/app_chat.py§wikipedia_fallback"
  - "GitHub Issue #811 + #813 / PR #812 + #814"
tags: ["rag", "chat", "wikipedia", "fallback", "mvp-1-8", "faz-2"]
aliases: ["controlled-wikipedia", "wikipedia-cta"]
---

# Wikipedia fallback — CONTROLLED

> **TL;DR:** Layer 1 (haber) yetersiz olduğunda Wikipedia kaynaklı cevap üretme; ama PRIMARY değil — kullanıcı CTA onayı zorunlu. Cevaplar her zaman kaynaklı (`source_type='wikipedia'` + `[W1]` citation). LLM kendi bilgi haznesinden ASLA cevap yok.

## Bağlam

Diğer AI (ChatGPT/Perplexity) önerisi: confidence düşükse Wikipedia'dan fallback yap. Ama Nodrat brand = "news intelligence". Wikipedia PRIMARY yaparsak generic assistant'a kayarız (Perplexity'nin "kara kutu" pozisyonu).

## Karar

3 katmanlı koşul:

1. **Score < T_low (0.40)** AND
2. **query_class != 'news_query'** (C2 STRICT) AND
3. **wikipedia.enabled = true** (admin tunable kill switch)

→ Stream short-circuit, `requires_user_consent` event emit, stub assistant message persist (content="", thinking_steps phase='consent_pending').

Kullanıcı **inline CTA card** ile (modal değil) 2 buton görür:
- "Evet, Wikipedia'dan bak" → `POST /chat/conversations/{id}/wikipedia-fallback {accepted: true}` → Wikipedia search + LLM cevap
- "Hayır, gerek yok" → `{accepted: false}` → kısa scope-aware refusal

## Wikipedia provider mimarisi

`apps/api/app/providers/wikipedia.py` (#811):

- **NOT** a `ModelProvider` — separate "knowledge provider" kategori
- Stateless `WikipediaProvider.search(query, lang, top_k)` + `.wikidata_factual(query, lang)`
- Wikipedia REST: opensearch + `/api/rest_v1/page/summary`
- Wikidata SPARQL: 8 factual property (P569 birth, P570 death, P1082 population, P571 founded, P36 capital, P39 position, P17 country, P102 party)
- Redis 24h cache (SHA1 + gün granülasyonu)
- `httpx.MockTransport` DI ile testable
- 13 unit test (#811)

## Lisans uyumu

- **CC BY-SA 4.0** — `WikiArticle.license` field yanıta dahil
- **25-kelime quote cap** — FSEK kuralımız (Türkiye telif), zaten prompt'a inject ediliyor
- **Citation format:** `[W1][W2]` (haber `[N]` ile karışmasın)
- `sources_used[].source_type='wikipedia'` + `source_name='Wikipedia (TR)'`

## UI/UX davranışı

| Mod | Badge | Source pill |
|---|---|---|
| Sadece haber | "Kaynak: Güncel haber arşivi" (default) | `[1] Anadolu Ajansı — title` (border) |
| Sadece Wikipedia | "Kaynak: Wikipedia" (secondary) | `📖 [W1] Wikipedia (TR) — title` (sarı tonlu) |
| Hybrid (gelecek) | "Kaynak: Haber + Wikipedia" (outline) | İkisi karışık |
| Yok | "Kaynak yok — konuşma context'inden" (outline) | (gizli) |

Component: `apps/web/src/components/chat/WikipediaConsentCard.tsx` (#813).

## Why CONTROLLED?

Önerilen alternatifler ve red sebepleri:

| Alternatif | Reddetme nedeni |
|---|---|
| **Wikipedia PRIMARY** | Brand contamination — Nodrat = haber, generic assistant'a kayar |
| **LLM kendi bilgisi fallback** | C1 — halüsinasyon riski, source-controlled value prop'u kaybeder |
| **Auto Wikipedia (CTA yok)** | Knowledge contamination — "Trump bugün ne dedi?" Wikipedia'ya düşebilir |
| **Wikipedia + paid Britannica** | C5 — ROI düşük, Wikipedia + Wikidata yeter |

## Hybrid path (insufficiency CTA)

T_low <= score < T_high durumunda: Layer 1 cevap üretilir + `insufficiency_signal` event emit (`InsufficiencySignal.tsx` banner). Kullanıcı "Wikipedia" tıklarsa: **yeni mesaj submit** edilir ("Aynı sorunun Wikipedia kaynaklı cevabını da göster") → planner general_knowledge → bu decision'ın path'i tetiklenir.

## İlişkiler

- Üst karar: [[tiered-knowledge-architecture]]
- Tetikleyici: [[confidence-based-routing]]
- News leak engelleme: [[news-first-strict-contamination-guard]]
- Provider: [[wikipedia-provider]] (entity)

## Açık sorular / gelecek

- Wikidata SPARQL coverage genişletme (P40 children, P3373 sibling, vb.) — opsiyonel
- Wikipedia paragraflar arası anlam bütünlüğü (extract'lar bazen kesik)
- TÜİK/TBMM API entegrasyonu (Türkiye-spesifik genel bilgi) — Faz 3 backlog

## Kaynaklar

- `apps/api/app/providers/wikipedia.py`
- `apps/api/app/api/app_chat.py:522+` (endpoint)
- `apps/web/src/components/chat/WikipediaConsentCard.tsx`
- GitHub Issue #811 + #813 / PR #812 + #814
