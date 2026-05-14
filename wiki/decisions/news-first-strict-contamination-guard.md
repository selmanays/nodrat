---
type: decision
title: "News-first STRICT — Wikipedia leak engelleme (contamination guard)"
slug: "news-first-strict-contamination-guard"
category: "rag"
status: "live"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "apps/api/app/api/app_chat_stream.py§hybrid_path_check"
  - "GitHub Issue #815 / PR #816"
tags: ["rag", "chat", "brand-integrity", "telemetry", "faz-2"]
aliases: ["news-strict-mode", "wikipedia-contamination-guard"]
---

# News-first STRICT

> **TL;DR:** `query_class='news_query'` durumunda Wikipedia ASLA tetiklenmez — brand contamination'ı engelleyen sert kural. "Trump bugün ne dedi?" sorusu Wikipedia'ya düşemez. Telemetry log ile invariant doğrulanır.

## Bağlam

Tiered architecture'da en büyük risk: **knowledge contamination**. Eğer "Trump bugün ne dedi?" gibi realtime sorgular Wikipedia'ya düşerse, kullanıcı Nodrat'ı "haber motoru" yerine "generic assistant" olarak algılar. Brand moat ölür.

## Karar

`query_class='news_query'` **hard gate** — bu durumda:

1. **Wikipedia CTA göstermez** — `should_offer_wikipedia` koşulunda `query_class != "news_query"` filter
2. **Hybrid insufficiency CTA göstermez** — banner sadece non-news için emit edilir
3. **Wikipedia provider çağrısı yapılamaz** — provider gate'in arkasında

Telemetry log:

```python
if query_class == "news_query":
    logger.info(
        "news_first_strict_ok: conv=%s wikipedia_used=False score=%s",
        conv_id, conf.score,
    )
```

Bu log girdisi C2 invariant'ı her sorguda doğrular. Eğer gelecekte bir bug Wikipedia provider'ı news_query path'inden tetiklerse, bu log entry mantıken çıkmamalı.

## Why STRICT?

- **Brand integrity:** Nodrat = realtime news intelligence. Generic assistant pozisyonu = differansiyel kayıp.
- **Knowledge contamination:** "Trump bugün ne dedi?" + Wikipedia karışırsa, "bu sistem hangi tür kaynaktan bilgi geliyor?" sorusu kullanıcıda belirsizleşir.
- **Source transparency:** "Kaynak: Güncel haber arşivi" badge mesaj başında — Wikipedia leak olursa bu söz boş kalır.

## Routing özeti

| query_class | Score | Path |
|---|---|---|
| news_query | herhangi | Layer 1 STRICT (Wikipedia leak yok) |
| general_knowledge | >= T_high | Layer 1 (haberlerde varsa) |
| general_knowledge | T_low <= s < T_high | Hybrid + insufficiency banner |
| general_knowledge | < T_low | Wikipedia CTA |
| meta_query | herhangi | Conversation context (retrieval atla) |
| mixed | >= T_high | Layer 1 |
| mixed | < T_high | Hybrid → kullanıcı Wikipedia isterse 2B |

`news_query` her durumda Layer 1'de kalır. Diğer 3 sınıf score'a göre rotalanır.

## Gelecek: ML-based contamination detection

Şu an heuristik (logger.info). Production verisi toplandıktan sonra:
- contamination_event counter (Prometheus)
- Günde >5 contamination → admin alert
- ML classifier (query → contamination_risk score) — uzun vade backlog

## İlişkiler

- Üst karar: [[tiered-knowledge-architecture]]
- Sınıflandırma: [[query-class-classification]]
- Wikipedia provider: [[wikipedia-fallback-controlled]]
- Confidence eşikleri: [[confidence-based-routing]]

## Kaynaklar

- `apps/api/app/api/app_chat_stream.py:wikipedia_enabled check + STRICT log`
- GitHub Issue #815 / PR #816
- Plan: `/Users/selmanay/.claude/plans/nerdi-in-ekilde-faz-2-unified-nebula.md` C2 locked constraint
