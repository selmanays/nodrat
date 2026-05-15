---
type: decision
title: "Wikipedia + Wikidata kombine knowledge source"
slug: "wikipedia-wikidata-knowledge-source"
category: "rag"
status: "live"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "apps/api/app/core/chat_tools.py (execute_search_wikipedia)"
  - "apps/api/app/providers/wikipedia.py"
  - "GitHub PR #825 #827(#828)"
tags: ["rag", "wikipedia", "wikidata", "knowledge-source", "mvp-1-8", "faz-2"]
aliases: ["wikidata-factual", "wikipedia-list-search"]
---

# Wikipedia + Wikidata kombine knowledge source

> **TL;DR:** `search_wikipedia` tool'u Wikipedia prose (anlatı/bağlam) + Wikidata structured facts (kesin değerler) PARALEL çeker. Wikipedia REST summary extract'i infobox verisini (doğum tarihi, nüfus, kuruluş yılı) İÇERMEZ — bu factual sorular Wikidata P-property'lerinde. Wikipedia search `opensearch` (prefix/autocomplete) yerine `list=search&srsort=relevance` (gerçek full-text motor) kullanır.

## Bağlam — iki ayrı sorun

### 1. opensearch yanlış sayfa getiriyordu (#825)

İlk implementasyon Wikipedia `opensearch` API'sini kullanıyordu — bu **prefix/autocomplete** için tasarlanmış, relevance sıralaması zayıf. Production'da "Donald Trump" araması "Donald Trump karşıtı protestolar" alt-konusunu ana entity sayfasından önce döndürdü. Düzeltme: `action=query&list=search&srsort=relevance` — Wikipedia'nın gerçek full-text arama motoru.

### 2. Wikipedia extract factual veri içermiyor (#827/#828)

TR Wikipedia "Donald Trump" REST summary extract'i: *"...47. başkanı olarak görev yapan siyasetçi..."* — **doğum tarihi YOK**. REST `/page/summary/` sadece giriş özetini verir, infobox'taki yapısal veriyi (doğum/ölüm/nüfus/kuruluş) içermez. "trump kaç yaşında" sorusunun cevabı tam da bu eksik veride. Sonuç: doğru sayfa gelse bile LLM "bilgi yok" diyordu.

## Karar

`execute_search_wikipedia` iki kaynağı **paralel** (`asyncio.gather`) çeker, kombine eder:

| Kaynak | Ne verir | Format |
|---|---|---|
| **Wikidata** (`wikidata_factual`) | Yapısal kesin değerler: P569 doğum, P570 ölüm, P1082 nüfus, P571 kuruluş, P36 başkent, P39 pozisyon, P17 ülke, P102 parti | `[W1] Wikidata — Donald Trump\n- Doğum tarihi: 1946-06-14` |
| **Wikipedia** (`search` list=search) | Anlatı/bağlam prose, top-3 sayfa | `[W2] Donald Trump (tr)\n<extract>` |

- Wikidata fact varsa **[W1] olarak başa** (kesin/doğrulanmış), Wikipedia prose offset'le W2'den
- ISO tarih (`1946-06-14T00:00:00Z`) → `1946-06-14` kısaltılır, LLM yaşı hesaplar
- LLM'e talimat: *"tarih/sayı için Wikidata yapısal verisini öncele"*
- Wikidata source: `source_type='wikipedia'`, `source_name='Wikidata'`, license CC0 1.0
- Hata izolasyonu: `return_exceptions=True` — biri patlarsa diğeri devam

## Why

- **Wikipedia ≠ Wikidata:** Wikipedia insan-yazımı ansiklopedi (prose, "neden iptal edildi" gibi anlatı); Wikidata makine-okunur yapısal DB (Q-ID + P-property, "kaç yaşında" gibi kesin değer). Tamamlayıcılar.
- **REST summary'nin sınırı yapısal:** Extract intro paragrafını özetler; infobox (doğum/nüfus) ayrı bir veri katmanı. Prose'dan factual veri ummak güvenilmez.
- **Wikidata cost $0:** SPARQL + wbsearchentities ücretsiz, Redis 24h cache.

## Alternatifler

| Alternatif | Reddetme nedeni |
|---|---|
| Sadece Wikipedia prose | Factual sorular ("kaç yaşında") extract'te yok → cevapsız |
| `prop=extracts&exintro` (uzun extract) | Yine infobox yok; bazı sayfalarda doğum lead'de değil |
| opensearch koru | Prefix matcher, relevance zayıf — yanlış sayfa |
| Sadece Wikidata | Anlatı/bağlam soruları ("neden iptal edildi") yapısal veride yok |

## İlişkiler

- Tool-use mimarisi: [[llm-tool-use-wikipedia]]
- Provider implementasyon: [[wikipedia-provider]]
- Üst mimari: [[tiered-knowledge-architecture]]
- Karar/vazgeçiş zinciri: [[chat-knowledge-evolution]]

## Kaynaklar

- `apps/api/app/core/chat_tools.py` (execute_search_wikipedia — gather kombine)
- `apps/api/app/providers/wikipedia.py` (`_search_lang` list=search, `wikidata_factual` SPARQL)
- GitHub PR #825 (list=search relevance) #827/#828 (Wikidata kombine)
