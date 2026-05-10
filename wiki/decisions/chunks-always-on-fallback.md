---
type: decision
title: "Chunks always-on fallback — agenda<3 ise chunks ekle"
slug: "chunks-always-on-fallback"
category: "rag"
status: "live"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/api/app_generate.py§525-545"
  - "GitHub Issue #617 / PR #624"
tags: ["rag", "retrieval", "fallback", "mvp-1-8"]
aliases: ["chunks-fallback", "supplementary-chunks"]
---

# Chunks always-on fallback

> **TL;DR:** Önceden agenda_cards=0 ise chunks denenirdi (singleton edge-case). Yeni: **agenda_cards<3 ise** chunks fallback dispatch edilir. Yeni article'lar agenda'a girmeden önce chunk seviyesinde bulunsun.

## Bağlam

Pipeline akışı: `cleaned → chunks → cluster_article → event_articles → agenda_card`. Yeni article'lar **kümeleme adımına gecikmeli** giriyor (cluster_article task kuyrukta bekleyebilir, ya da [#611] auto-dispatch eksikliği). Bu sırada:
- Article cleaned ✅
- Chunks var ✅
- event_articles=0 ❌ (cluster yok)
- agenda_card YOK → RAG göremez

Üretim vakası: Bianet "Azıcık radyasyon kemiklere yararlıdır" article cleaned + chunks=1 ama event_articles=0. agenda search bulamadı, kullanıcı "yetersiz veri" gördü.

## Tasarım

```python
needs_chunks = len(agenda_cards) < 3
if needs_chunks:
    supplementary_chunks = await hybrid_search_chunks(
        db, query_text=enriched_query, query_vector=query_vec,
        top_k=max(4, content_top_k - len(agenda_cards)),
        candidate_pool=candidate_pool,
        since_hours=168,  # son 7 gün
    )
```

- agenda<3: muhtemel "yeni" article eksikliği
- chunks 7-gün penceresi: eski içerikten gürültü çekmesin
- top_k = mevcut agenda eksiği kadar (ek 4 minimum)

## Önceki davranış (#393 MVP-2.1)

```python
if not agenda_cards:  # sadece 0 ise
    supplementary_chunks = await hybrid_search_chunks(top_k=4, ...)
```

Bu, agenda=2 ama yeterli değil durumlarında chunks denemiyordu — yeni article'lar görünmez kalıyordu.

## Etki

- Bianet "azicik" article: agenda 0, chunks fallback ile bulundu
- Bayraktar TB3: agenda 0, 4 chunks (yeni eklenen kaynaklar)
- Trade-off: latency +50-100ms (1 ek SQL)

## İlişkiler

- [[multi-query-rewrite]] — variant-based search sonrası fallback
- [[source-diversity-cap]] — chunks da diversity filter'a girer

## Kaynaklar

- `apps/api/app/api/app_generate.py` §525-545
- [PR #624](https://github.com/selmanays/nodrat/pull/624)
- [#611 cluster auto-dispatch takip](https://github.com/selmanays/nodrat/issues/611)
