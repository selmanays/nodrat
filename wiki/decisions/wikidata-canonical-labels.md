---
type: decision
title: "Wikidata/Wikipedia canonical-etiket ankrajı (küme+trend SENKRON)"
slug: "wikidata-canonical-labels"
status: live
created: 2026-06-22
updated: 2026-06-22
sources:
  - "GitHub #1710 (Faz 1 motor), PR #1711"
  - "GitHub #1712 (Faz 2 sync), PR #1712"
tags: [entities, trends, clusters, canonicalization, wikidata]
aliases: ["wikidata canonical", "küme trend senkron"]
---

## TL;DR
Küme + trend etiketleri **her zaman Wikipedia başlığı karşılığı** olur; korpus yüzey formları + Wikidata alias'ları `entity_aliases` olarak yakalanır. Founder isteği (2026-06-21): "Filenin Sultanları" → canonical **"Türkiye kadın millî voleybol takımı"** (alias); "ABD" → **"Amerika Birleşik Devletleri"**. Otorite sırası: **admin > wikidata > seed > token_subset > ham**. [[entity-canonicalization-faz1]]'i harici-otorite ile genişletir.

## Bağlam / neden
Trend ve küme etiketleri **senkron değildi** (founder şikayeti): küme etiketi her zaman canonical'a düşer ([[global-research-cluster-model]] ENTITY_DF_SQL) ama trend `trends.canonical_entities.enabled` flag'ine bağlıydı (default OFF → ham yüzey) + `cluster_link.py` (gaps/radar) canonical'ı hiç kullanmıyordu → aynı varlık kümede "Cumhuriyet Halk Partisi", trendde "CHP". Ayrıca canonical adlar seed-küratör / NER-mode-yüzey'den geliyordu (Wikipedia-otoriter değil).

## Mekanizma (3 faz)

**Faz 1 — zenginleştirme motoru (#1710/PR#1711, CANLI):**
- Offline Celery beat (`tasks.entities.enrich_wikidata`, 6h, ner_queue): `entities`'ten df≥min_freq + çözülmemiş yüzey → mevcut [[wikipedia-provider|WikipediaProvider]] zinciri (full-text → DOĞRU sayfa → `wikidata_qid_for_title` sitelink-deterministik QID → yeni `wikidata_entity_meta` wbgetentities labels|aliases|sitelinks|claims) → **tip-gate** (`wikidata_match.type_matches`: person Q5 ŞART; place/org/event insan/tarih=RED) → `canonical_entities` (canonical_name = Wikipedia TR başlık, source='wikidata') + `entity_aliases` (korpus yüzey + Wikidata TR alias'ları).
- **#997 dersi:** çıplak-keyword `wbsearchentities` QID disambiguation güvenilmez ("15 temmuz"→takvim) → MUTLAKA önce Wikipedia full-text → sayfa → wikibase_item.
- `wikidata_entity_resolutions` tablosu (raw-SQL-only, additive): **'denendi' guard** ([[ner-backfill-cost-loop|#1602 dersi]]) + cache. Flag `entities.wikidata_enrich.enabled` (prod AÇIK).
- Authority guard: alias ON CONFLICT admin+wikidata korur; `build_canonical` WHERE `NOT IN ('admin','wikidata')`.

**Faz 2 — sync (#1712/PR#1712, CANLI):**
- `trends.canonical_entities.enabled` default OFF→**ON** (kill-switch korunur).
- `cluster_link.py` 8 sorgu canonical-aware (`_CANON_JOIN` + `_NORM_EXPR` COALESCE): cluster_key artık `kebab(COALESCE(canonical_normalized, entity_normalized))` → küme resolver ile **BİREBİR** (Wikidata-canonical kümeler trend rozetini kaybetmez).
- Sonuç: küme + trend + radar **tek Wikipedia-temelli canonical**'dan okur.

**Faz 3 — retro-fit (PLANLI, ayrı, veri-mutasyonu onayı):** mevcut kümelerin DONMUŞ `ResearchCluster.canonical_name`'i (ON CONFLICT DO NOTHING, hiç UPDATE yok) Wikipedia başlığına relabel + gereken küme-merge. Mapping `entity_aliases` seviyesinde yapılmalı (cluster_key kebab-norm'dan türer; Wikidata farklı canonical_normalized'a maplerse key değişir → bölünme riski).

## Doğrulama (prod e2e)
Faz 1: Filenin Sultanları→Türkiye kadın millî voleybol takımı · ABD→Amerika Birleşik Devletleri · CHP→Cumhuriyet Halk Partisi · 15 temmuz→type_mismatch (red); top-8 korpus 8/8; canary 15→14 resolved+1 no_match. Faz 2: ABD entity → `place:amerika-birlesik-devletleri` (cur=1788), ham `place:abd` eşleşmez; trend tarafı küme ile aynı canonical anahtar.

## Alternatifler ve neden reddedildi
- **Deterministik fuzzy (trigram/word_similarity):** prod'da gürültülü (#1705 anchor genericliğinde de görüldü) — Wikipedia full-text + sitelink-QID daha kesin.
- **Çıplak wbsearchentities:** #997 spike negatif (disambiguation güvenilmez).
- **Faz 2'siz sadece Faz 1:** sync getirmez (trend flag OFF + cluster_link raw) → Faz 2 şart.

## İlişkiler
[[entity-canonicalization-faz1]] (genişletir — seed/token_subset/admin) · [[global-research-cluster-model]] (küme çapa/etiket) · [[clusters-trends-integration-2026-06]] (trend↔küme köprüsü) · [[wikipedia-provider]] (HTTP zinciri) · [[finding_research_critical_entity_mvp_filter|#1703]] (voleybol — bu mekanizma destekler).

## Kaynaklar
- GitHub [#1710](https://github.com/selmanays/nodrat/issues/1710) / PR [#1711](https://github.com/selmanays/nodrat/pull/1711) — Faz 1 motor.
- GitHub #1712 / PR [#1712](https://github.com/selmanays/nodrat/pull/1712) — Faz 2 sync.
- #997 (wikidata retrieval spike — negatif, merge-edilmedi; ders kaynağı).
