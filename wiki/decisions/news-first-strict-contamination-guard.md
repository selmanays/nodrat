---
type: decision
title: "News-first STRICT — Wikipedia leak engelleme (contamination guard)"
slug: "news-first-strict-contamination-guard"
category: "rag"
status: "live"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "apps/api/app/api/app_chat_stream.py (offer_tools gating)"
  - "GitHub Issue #815 / PR #816 → #823 (mekanizma değişti)"
tags: ["rag", "chat", "brand-integrity", "telemetry", "faz-2"]
aliases: ["news-strict-mode", "wikipedia-contamination-guard"]
---

# News-first STRICT

> **TL;DR (GÜNCEL — #823):** C2 invariant'ı KORUNDU ama mekanizma **tool-level gating**'e geçti: `query_class == 'news_query'` ise `search_wikipedia` tool LLM'e **hiç verilmez** (`offer_tools = wikipedia_enabled and query_class != "news_query"`). "Trump bugün ne dedi?" haber arşivinden cevaplanır, Wikipedia'ya düşemez (tool yok). Brand contamination koruması = tool sunum kontrolü.
>
> **Mekanizma evrimi:** PR #816 query_class hard-gate routing → #818 confidence skoru gate → #823 **tool-level gating** (güncel). Invariant hep aynı (news_query → Wikipedia leak yok); uygulama 3 kez değişti. Detay: [[llm-tool-use-wikipedia]].

> **TL;DR (tarihsel #818):** Wikipedia tetikleyicisi sadece confidence skoru — query_class hard-gate değil. Confidence yüksekse (>= T_high) Wikipedia OTOMATIK tetiklenmez. (Bu confidence-routing mimarisi #823'te terk edildi — [[confidence-based-routing]].)

> 🟥 **GÜNCEL DURUM (#845+, denetim 2026-05-15 kod-doğrulandı — bu satır
> yukarıdaki TÜM TL;DR/notları ve aşağıdaki gövdeyi SUPERSEDE eder):**
> Kodda `offer_tools` değişkeni / `query_class != "news_query"` tool-gating
> **YOK**. Gerçek kod: `tools_arg = CHAT_TOOL_DEFINITIONS if wikipedia_enabled
> else [SEARCH_NEWS_TOOL]` — `wikipedia.enabled` true iken **her iki tool da**
> (`search_news`+`search_wikipedia`) LLM'e her sorgu için sunulur. **C2
> (news-first) invariant'ı artık `SYSTEM_PROMPT_NODRAT_AGENT` ile korunur**
> (search_news BİRİNCİL / news-first talimatı), tool-gating ile DEĞİL.
> Confidence skoru / T_high / T_low / CTA / banner / `_stream_meta_query_answer`
> **terk edildi**; `contamination_event` telemetrisi kodda **mevcut değil**
> (hiç emit edilmez). Bu sayfanın gövdesi (#810/#814/#816/#818/#823 notları
> dahil) **tarihsel evrim** kaydıdır — güncel mekanizma:
> [[agentic-generate-orchestration]] + [[llm-tool-use-wikipedia]].

## Bağlam

Tiered architecture'da en büyük risk: **knowledge contamination**. Eğer "Trump bugün ne dedi?" gibi realtime sorgular Wikipedia'ya düşerse, kullanıcı Nodrat'ı "haber motoru" yerine "generic assistant" olarak algılar. Brand moat ölür.

İlk implementasyonda (#810/#814) çift gate vardı: `query_class != "news_query"` AND `score < T_low`. Production'da "trump kaç yaşında" sorusu **news_query** olarak sınıflandırıldı (planner accuracy hatası). Sonuç: confidence düşük olmasına rağmen Wikipedia CTA tetiklenmedi, kullanıcı "kaynaklarda yok" cevabı aldı. (#818 bug)

## Karar (revised #818)

Wikipedia gate'i **tek koşul:** `confidence.score < T_low`. query_class artık sadece intent telemetri/UI hint (routing değil).

```python
# YENİ (#818):
should_offer_wikipedia = (
    conf is not None
    and conf.score < t_low
    and wikipedia_enabled
)

# ESKİ (#810/#814, kaldırıldı):
# should_offer_wikipedia = ... AND query_class != "news_query"
```

### Neden bu invariant brand'i korur?

| Senaryo | Confidence | Davranış |
|---|---|---|
| "Trump bugün ne dedi?" (haberlerde GERÇEKTEN var) | semantic + entity_match + recency yüksek → **score >= T_high** | Layer 1 STRICT, Wikipedia OTOMATIK tetiklenmez |
| "Trump kaç yaşında?" (haberlerde Trump var ama yaş yok) | semantic var ama entity_match ("yaş") düşük → **score < T_low** | Wikipedia CTA tetiklenir |
| "Trump'ın Çin politikası tarihte" (mixed) | orta skor | Hybrid banner — kullanıcı seçer |

Brand contamination, mimari olarak `score >= T_high` koşulu tarafından engellenir. **Planner yanlış sınıflandırsa bile** sistem doğru rotalanır.

Telemetry log (STRICT path doğrulama):

```python
if conf.score >= t_high:
    logger.info(
        "news_first_strict_ok: conv=%s wikipedia_used=False score=%.3f query_class=%s",
        conv_id, conf.score, query_class,
    )
```

## Why STRICT?

- **Brand integrity:** Nodrat = realtime news intelligence. Generic assistant pozisyonu = differansiyel kayıp.
- **Knowledge contamination:** "Trump bugün ne dedi?" + Wikipedia karışırsa, "bu sistem hangi tür kaynaktan bilgi geliyor?" sorusu kullanıcıda belirsizleşir.
- **Source transparency:** "Kaynak: Güncel haber arşivi" badge mesaj başında — Wikipedia leak olursa bu söz boş kalır.

## Routing özeti (#818 revised)

| Score | Davranış | query_class etkisi |
|---|---|---|
| `score >= T_high` | Layer 1 STRICT (Wikipedia OTOMATIK tetiklenmez) | Telemetri/UI hint, routing yok |
| `T_low <= score < T_high` | Layer 1 cevap + insufficiency banner | Telemetri/UI hint |
| `score < T_low` | Wikipedia CTA | Telemetri/UI hint |
| (`query_class='meta_query'`) | Retrieval atla, conversation context | Sadece bu durumda routing-relevant |

`meta_query` haricinde tüm path'ler **score-driven**. query_class artık sadece prompt context + UI badge için (insight, routing değil).

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
