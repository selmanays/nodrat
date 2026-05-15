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
  - "GitHub PR #825 #827(#828) #851 #863"
tags: ["rag", "wikipedia", "wikidata", "knowledge-source", "mvp-1-8", "faz-2"]
aliases: ["wikidata-factual", "wikipedia-list-search"]
---

# Wikipedia + Wikidata kombine knowledge source

> **TL;DR:** `search_wikipedia` tool'u Wikipedia prose (anlatı/bağlam) + Wikidata structured facts (kesin değerler) birlikte sunar. Wikipedia REST summary extract'i infobox verisini (doğum/ölüm/nüfus/kuruluş) İÇERMEZ — bu factual sorular Wikidata P-property'lerinde. **#863 bulletproof zincir (SIRALI, paralel `gather` kaldırıldı):** Wikipedia full-text (`list=search`, niteleyiciye toleranslı → doğru SAYFA) → o sayfanın `pageprops.wikibase_item`'ı (DİL-BAĞIMSIZ kesin QID) → `wbgetentities` **Action API** ile claim'ler. Fuzzy `wbsearchentities` ve flaky `query.wikidata.org/sparql` endpoint elendi.

## Bağlam — iki ayrı sorun

### 1. opensearch yanlış sayfa getiriyordu (#825)

İlk implementasyon Wikipedia `opensearch` API'sini kullanıyordu — bu **prefix/autocomplete** için tasarlanmış, relevance sıralaması zayıf. Production'da "Donald Trump" araması "Donald Trump karşıtı protestolar" alt-konusunu ana entity sayfasından önce döndürdü. Düzeltme: `action=query&list=search&srsort=relevance` — Wikipedia'nın gerçek full-text arama motoru.

### 2. Wikipedia extract factual veri içermiyor (#827/#828)

TR Wikipedia "Donald Trump" REST summary extract'i: *"...47. başkanı olarak görev yapan siyasetçi..."* — **doğum tarihi YOK**. REST `/page/summary/` sadece giriş özetini verir, infobox'taki yapısal veriyi (doğum/ölüm/nüfus/kuruluş) içermez. "trump kaç yaşında" sorusunun cevabı tam da bu eksik veride. Sonuç: doğru sayfa gelse bile LLM "bilgi yok" diyordu.

### 3. Wikidata erişimi sistemik kırık — fuzzy search + flaky SPARQL (#863)

#827/#828 Wikidata'yı eklemişti ama niteleyici içeren biyografik sorular (`conv 2c9bb90a` "Robert C. Cooper kaç yaşında / doğum tarihi") "doğum tarihi yok" dönüyordu — `Q431432 P569=1968-10-14` VERİ VAR olmasına rağmen. İki kök neden:

- **(a) Ham query → fuzzy `wbsearchentities`:** `wikidata_factual` ham kullanıcı sorgusunu fuzzy entity aramasına veriyordu. `wbsearchentities("Robert C. Cooper")`→Q431432 ✓ ama `wbsearchentities("Robert C. Cooper doğum tarihi")`→**BOŞ** (niteleyici kelime fuzzy match'i kırar). Sorun entity-spesifik değil — niteleyici içeren **TÜM** biyografik factual sorular sistemik kırık.
- **(b) SPARQL flaky:** `query.wikidata.org/sparql` prod'da 400/502 dönüyordu (3rd-party endpoint güvenilmez).

Sinyal dersi: "doğru Wikipedia kaynağını buldu ama cevap veremedi" = **veri-yolu kırığı** (prompt sorunu değil). Prompt'a dokunmadan veri yolu onarılır.

## Karar

`execute_search_wikipedia` **sıralı bulletproof zincir** yürütür (#863 — paralel `asyncio.gather` kaldırıldı; entity resolution Wikipedia sonucuna bağımlı olduğu için sıralı zorunlu):

1. **Wikipedia full-text** (`search`, `list=search&srsort=relevance`) — niteleyiciye toleranslı motor; "Robert C. Cooper doğum tarihi" → doğru ana SAYFA (`Robert C. Cooper`).
2. **Sitelink → QID** (`wikidata_qid_for_title`): bulunan sayfanın `prop=pageprops&ppprop=wikibase_item`'ı → **dil-bağımsız kesin QID** (Q431432). Fuzzy arama / ambiguity yok.
3. **wbgetentities** (`wikidata_factual(qid=...)`): Action API (`action=wbgetentities&ids={qid}&props=claims|labels`) → `WIKIDATA_FACTUAL_PROPS` claim'leri. QID verildiğinde fuzzy `wbsearchentities` ATLANIR (sitelink QID yoksa fallback). SPARQL hiç çağrılmaz.

| Kaynak | Ne verir | Cite (#851 tek `[n]` namespace) |
|---|---|---|
| **Wikidata** (`wikidata_factual`) | Yapısal kesin değerler: P569 doğum, P570 ölüm, P1082 nüfus, P571 kuruluş, P36 başkent, P39 pozisyon, P17 ülke, P102 parti | `[1] Wikidata — Donald Trump\n- Doğum tarihi: 1946-06-14` |
| **Wikipedia** (`search` list=search) | Anlatı/bağlam prose, top-3 sayfa | `[2] Donald Trump (tr)\n<extract>` |

- Wikidata fact varsa **[1] olarak başa** (kesin/doğrulanmış), Wikipedia prose sonra. #851 ile `[W]` prefix kaldırıldı — haber `[n]` ile **tek global namespace**; `cite_start` offset multi-round çakışmayı önler.
- ISO tarih (`1946-06-14T00:00:00Z` veya `+1946-...` lstrip `+`) → `1946-06-14`; LLM yaşı hesaplar
- LLM'e talimat: *"tarih/sayı için Wikidata yapısal verisini öncele"*
- Wikidata source: `source_type='wikipedia'`, `source_name='Wikidata'`, `url=https://www.wikidata.org/wiki/{QID}`, license CC0 1.0
- Hata izolasyonu: Wikidata adımı patlasa/boş dönse Wikipedia prose tek başına servis edilir (zincir hata-toleranslı)

## Why

- **Wikipedia ≠ Wikidata:** Wikipedia insan-yazımı ansiklopedi (prose, "neden iptal edildi" gibi anlatı); Wikidata makine-okunur yapısal DB (Q-ID + P-property, "kaç yaşında" gibi kesin değer). Tamamlayıcılar.
- **REST summary'nin sınırı yapısal:** Extract intro paragrafını özetler; infobox (doğum/nüfus) ayrı bir veri katmanı. Prose'dan factual veri ummak güvenilmez.
- **Wikidata cost $0:** Action API (`wbgetentities`/`wbsearchentities`) + `pageprops` ücretsiz, Redis 24h cache.
- **Deterministik entity resolution (#863):** Wikipedia sayfa başlığının `wikibase_item`'ı dil/niteleyici/ambiguity'den bağımsız KESİN QID verir; fuzzy `wbsearchentities` ham sorguda kırılgan. Entity'yi deterministik kaynaktan çöz (sitelink > fuzzy search).
- **Flaky 3rd-party'den kaç (#863):** `query.wikidata.org/sparql` prod'da 400/502; aynı veriyi veren güvenilir Action API (`wbgetentities`, `wbsearchentities` ile aynı `api.php` endpoint) varken flaky servise bağımlı kalma.

## Alternatifler

| Alternatif | Reddetme nedeni |
|---|---|
| Sadece Wikipedia prose | Factual sorular ("kaç yaşında") extract'te yok → cevapsız |
| `prop=extracts&exintro` (uzun extract) | Yine infobox yok; bazı sayfalarda doğum lead'de değil |
| opensearch koru | Prefix matcher, relevance zayıf — yanlış sayfa |
| Sadece Wikidata | Anlatı/bağlam soruları ("neden iptal edildi") yapısal veride yok |
| Ham query → `wbsearchentities` (fuzzy) | Niteleyici ("doğum tarihi") fuzzy entity match'i kırar → factual cevapsız; sitelink QID deterministik (#863) |
| Wikidata SPARQL (`query.wikidata.org`) | Prod'da flaky 400/502; aynı veri güvenilir `wbgetentities` Action API'de (#863) |
| Paralel `asyncio.gather` koru | Adım 2 (sitelink QID) Wikipedia sonucuna bağımlı → sıralı zorunlu (#863) |

## İlişkiler

- Tool-use mimarisi: [[llm-tool-use-wikipedia]]
- Provider implementasyon: [[wikipedia-provider]]
- Üst mimari: [[tiered-knowledge-architecture]]
- Karar/vazgeçiş zinciri: [[chat-knowledge-evolution]]

## Kaynaklar

- `apps/api/app/core/chat_tools.py` (`execute_search_wikipedia` — sıralı zincir: search → qid_for_title → wikidata_factual(qid); `cite_start` #851)
- `apps/api/app/providers/wikipedia.py` (`search` list=search; `wikidata_qid_for_title` `pageprops.wikibase_item` sitelink; `wikidata_factual` `wbgetentities` Action API — SPARQL kaldırıldı)
- GitHub PR #825 (list=search relevance) #827/#828 (Wikidata kombine) #851 (tek `[n]` namespace + cite_start) #863 (bulletproof: sitelink QID + wbgetentities, SPARQL/fuzzy elendi)
