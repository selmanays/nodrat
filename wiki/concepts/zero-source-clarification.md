---
type: concept
title: "0-kaynak sorgu netleştirme (LLM niyet-anlama)"
slug: "zero-source-clarification"
status: live
created: 2026-06-22
updated: 2026-06-22
sources:
  - "GitHub #1701 / PR #1702"
tags: [research, clarification, llm, citation-safe]
aliases: ["clarification", "niyet-anlama", "did you mean"]
---

## TL;DR
Araştırma korpusunda sorguya **dayanak kaynak bulunamadığında** (0-kaynak), bland "bulamadım" yerine ucuz bir LLM (v4-flash) **kullanıcının niyetini anlamaya** çalışıp kısa açıklama + 2-3 yeniden-ifade/netleştirme önerisi üretir. Öneriler mevcut **followup-chip** mekanizmasıyla gösterilir (tıkla → yeni sorgu). Citation-safe: olgusal iddia UYDURMAZ — yalnız netleştirme. Flag `research.clarification.enabled` (prod AÇIK).

## Tanım / Bağlam
Founder isteği (#1701): "Nodrat standardında cevap üretilemeyen/anlaşılmayan sorgu, normal cevap yerine kullanıcının neyi kastettiğini anlamaya çalışıp öneri sunabilir." [[research-cited-only-hard-invariant|Cited-only invariant]] gereği 0-kaynakta uydurma cevap yasak; bu mekanizma o boşluğu netleştirmeyle doldurur.

## Mekanizma
- **Tetikleme** (`app_research_stream`, satır ~1232): `_cited_only_strict` **VE** `not all_sources` **VE** `_is_substantive(final_text)` (gerçek 0-kaynak; tangential kaynak bulunan sorgu tetiklemez → orada dürüst-refüze yolu çalışır).
- **Üretim:** `generate_clarification` (`modules/generations/query_clarification.py`) → v4-flash (`route_for_tier`), prompt `query_clarification` (admin-tunable, `prompts_store`), max_tokens=300/temp=0.4, best-effort cost-log (`track_provider_call(operation="clarification")`), `asyncio.wait_for` timeout=10s.
- **Çıktı + parse:** satır-bazlı tolerant parse (`prompts/query_clarification.parse_clarification`) — JSON DEĞİL (küçük-model JSON güvenilmezliği #819/#840). `MESAJ:` satırı → mesaj; `- `/`*`/`•` satırları → öneriler (dedupe, limit 3). Mesaj yoksa → None (caller degrade eder).
- **Gösterim:** `final_text = mesaj`; öneriler **followup_suggestions** slotuna konur (mevcut chip persist+emit+UI yeniden kullanılır → yeni SSE event/frontend YOK).

## Kararlar
- **LLM > deterministik fuzzy:** "did you mean" için trigram/word_similarity prod'da test edildi → **gürültülü** ('MA'/'Zambak'/jenerik dominasyonu; uzun özel-adlar düşük skor). Founder LLM niyet-anlamayı seçti (asıl hedef "neyi kastettiğini anla").
- **Citation-safe:** ayrı best-effort call; olgusal iddia ana cevaba sızmaz; prompt "ASLA cevap/tarih/sayı UYDURMA" der; typo-düzeltme yapar ("kuantm bilgisyar"→"Kuantum bilgisayar").
- **Gerçek-0-kaynak NADİR:** geniş korpus çoğu sorguya tangential kaynak bulur → orada cited-only dürüst-refüze devrede; clarification yalnız sıfır-kaynak edge'inde.

## İlişkiler
[[research-cited-only-hard-invariant]] (0-kaynakta uydurma yasağı — bu mekanizmanın önkoşulu) · [[research-retrieval-transparency]] · [[provider-call-logging-coverage]] (clarification cost-log) · [[global-research-cluster-model]].

## Kaynaklar
- GitHub [#1701](https://github.com/selmanays/nodrat/issues/1701) / PR [#1702](https://github.com/selmanays/nodrat/pull/1702).
- docs: prompt-contracts §"Prompt — Query Clarification" + api-contracts (research stream `followup_suggestions`).
