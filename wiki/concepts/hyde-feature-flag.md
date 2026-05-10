---
type: concept
title: "HyDE feature flag — Hypothetical Document Embeddings (gradual rollout)"
slug: "hyde-feature-flag"
category: "rag"
status: "live (off by default)"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/api/app_generate.py§408-450"
  - "GitHub Issue #621 / PR #627"
tags: ["rag", "retrieval", "hyde", "feature-flag", "mvp-1-8"]
aliases: ["hypothetical-doc-embed"]
---

# HyDE feature flag

> **TL;DR:** Hypothetical Document Embeddings — DeepSeek'a sorgu için 1-2 cümlelik hipotetik haber başlığı + lead üretttirilir, embed edilir, RRF füzyonuna ek varyant olarak girer. **Feature flag ile A/B rollout** (`retrieval.hyde_enabled`, default OFF).

## Bağlam

Sorgu-cevap asimetrisi RAG'ın bilinen sorunudur:
- **Kullanıcı sorgusu:** kısa, soyut, anahtar kelime ("F-16 21 ülke kim")
- **Article başlığı/içeriği:** uzun, somut, cümle ("Northrop Grumman 21 ülkenin F-16 radarları için 488 milyon dolarlık sözleşme kazandı")

Embedding similarity bu asimetri yüzünden zayıf çıkabilir. HyDE çözümü: önce LLM'e **hipotetik cevap** ürettir (cümle/paragraf), sonra onu embed et → cümle-cümle similarity → article uzayına yakın.

[Pinecone HyDE blog](https://www.pinecone.io/learn/hyde/) ve [Perplexity benzeri sistemlerde](https://ziptie.dev/blog/how-perplexity-ai-answers-work/) yaygın pattern.

## Implementation

```python
hyde_enabled = await settings_store.get_bool(db, "retrieval.hyde_enabled", False)
if hyde_enabled:
    chat_provider = registry.route_for_tier(operation="chat", tier="free")
    hyde_prompt = (
        "Aşağıdaki sorguya 1-2 cümlelik hipotetik bir haber başlığı + "
        "açılış cümlesi üret. Gerçek olmak zorunda değil — sorgunun "
        "semantic uzayını yakalayan bir tahmin."
        f"\n\nSorgu: {plan.topic_query}\n\nHipotetik haber:"
    )
    hyde_resp = await chat_provider.generate_text(...)
    hyde_doc = hyde_resp.text
    if hyde_doc:
        query_variants.append(hyde_doc)
```

HyDE varyantı kendi embedding'i ile dense+sparse arama yapar (ek paralel embedding call).

## Cost analizi

- **LLM call:** +1 DeepSeek (~120 tokens, ~$0.0001 marjinal)
- **Embedding call:** +1 local bge-m3 (~0$ marjinal)
- **Latency:** +600-900ms (LLM + embedding paralel)

## Feature flag rationale

Default OFF — rollout stratejisi:
1. **Şimdi:** OFF, A/B için hazır
2. **Faz 1 (örn. 1 hafta):** belirli kullanıcılar (admin) AÇ
3. **Faz 2:** tüm Pro+ kullanıcılarda AÇ (cost takibi)
4. **Faz 3:** tüm tier'larda AÇ (eğer kalite kazanımı maliyeti haklı kılıyorsa)

Aktivasyon: `/admin/settings` → `retrieval.hyde_enabled=true`

## İlişkiler

- [[multi-query-rewrite]] — HyDE 4. varyant olarak girer
- [[multi-source-synthesis]] — HyDE recall artırır, sentez kalitesi yükselir
- [[deepseek-default-llm]] — HyDE LLM call'u DeepSeek üzerinden

## Kaynaklar

- `apps/api/app/api/app_generate.py` §408-450
- [PR #627](https://github.com/selmanays/nodrat/pull/627)
- [Pinecone HyDE blog](https://www.pinecone.io/learn/hyde/)
