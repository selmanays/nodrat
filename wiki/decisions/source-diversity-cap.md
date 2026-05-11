---
type: decision
title: "Source diversity cap — aynı domain'den max 2 kart"
slug: "source-diversity-cap"
category: "rag"
status: "live"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/api/app_generate.py§490-525"
  - "GitHub Issue #616 / PR #624"
tags: ["rag", "retrieval", "diversity", "anti-hallucination", "mvp-1-8"]
aliases: ["domain-cap", "source-cap"]
---

# Source diversity cap

> **TL;DR:** RAG retrieval sonuçlarında **aynı domain'den max 2 kart** kabul edilir. Tek-kaynak halüsinasyon riskini azaltır + kaynak çeşitliliği sağlar. Multi-query RRF sonrası uygulanır, top_k * 2 pull → diversity filter → final top_k.

## Bağlam

Kaynak sayısı 6 → 27'ye çıkınca yüksek-volume kaynaklar (Hürriyet, Habertürk) RAG sonuçlarını domine etmeye başladı. 5 sonuç hep Habertürk'ten gelirse:
- Kullanıcıya tek-perspektif (mainstream gazete)
- Halüsinasyon riski (tek kaynak yanlış olursa generation yine onu kullanır)
- Perplexity kalitesinden uzaklaşma (Perplexity 3-5 kaynak çeşitliliği önerir)

## Tasarım

```python
agenda_cards_raw = await hybrid_search(top_k=content_top_k * 2)  # 20 raw
domain_counts = {}
agenda_cards = []
for card in agenda_cards_raw:
    domain = card.get("source_domain", "").lower()
    if not domain or domain_counts.get(domain, 0) < 2:
        agenda_cards.append(card)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
    if len(agenda_cards) >= content_top_k:
        break
```

- 2× pull (top_k * 2 = 20)
- Per-domain counter (max 2)
- top_k'ya dolunca break

## Trade-off

**Pro:**
- Kaynak çeşitliliği (mainstream + bağımsız + sektörel)
- Tek-kaynak halüsinasyon riski azalır
- Perplexity-style multi-perspective summary için zemin

**Con:**
- Recall düşebilir (eğer en alakalı 5 kart aynı domain'den ise sadece 2 alınır)
- Niş konularda (sadece 1 kaynak yazıyor) etkisiz

## Etki

Üretim ölçümü: 20-sorgu smoke testte source diversity uygulandığında ortalama 3-4 farklı domain'den kart geliyor (önceden 1-2). Halüsinasyon vakası gözlemlenmedi.

## İlişkiler

- [[multi-query-rewrite]] — RRF sonrası diversity filter uygulanır
- [[multi-source-synthesis]] — diversity → çeşitli perspektif → sentez kalitesi
- [[chunks-always-on-fallback]]
- [[chunks-first-retrieval]]
- [[cross-source-agreement]]
- [[smart-quote-normalization]]

## Kaynaklar

- `apps/api/app/api/app_generate.py` §490-525
- [PR #624](https://github.com/selmanays/nodrat/pull/624)
