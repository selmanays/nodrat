---
type: concept
title: "NER gürültü stopword filtresi — common-word mis-NER enforcement"
slug: "ner-noise-stopword-filter"
status: live
created: 2026-06-18
updated: 2026-06-18
sources:
  - "apps/api/app/core/entity_noise.py"
  - "apps/api/app/modules/entities/tasks/entities.py§INSERT"
  - "apps/api/app/core/research_clustering.py§select_canonical_anchor"
tags: [ner, entities, clustering, trends, data-quality]
aliases: ["entity-noise", "ner-stopword", "common-word-mis-ner"]
---

# NER gürültü stopword filtresi — common-word mis-NER enforcement

## TL;DR

NER prompt'u "generic/günlük kelimeler atlanır (haber, bugün, çarşamba, vatandaş)"
der; ama ucuz model (DeepSeek v4-flash) her zaman uymaz → "var"(org)/"bugün"/"zaman"
gibi function/generic kelimeler entity etiketlenir. `core/entity_noise.is_noise_entity`
bu prompt kuralının **deterministik kod-enforcement'ı**: tek paylaşımlı katman hem **NER
ingest'inde** (yeni gürültüyü engelle) hem **küme çapasında** (mevcut gürültüyü çapa-dışı
bırak) kullanılır → trend ve küme **aynı temiz entity tabanını** paylaşır (#1598).

## Neden var

Trend ve küme çapası aynı `entities` korpusunu okur ([[clusters-trends-integration-2026-06]]).
[[global-research-cluster-model]] §Çapa seçimi #1594 ile rarest→GATE+prominence geçti →
gürültünün çoğu temizlendi; ama "var"(df5/4-kaynak) gibi **gate'i geçecek kadar tutarlı
mis-NER** kaldı. Kullanıcı: "trend sistemiyle küme sistemi aynı mantıkla çalışsın" — bu da
NER'in **kaynakta** temiz olmasını gerektirir (consumption-stoplist band-aid değil, ingest
enforcement). Trend tarafı bu kelimeleri hacimle gömerken (görünmez) küme tek-entity'li
sorguyu onlara çapalıyordu → tek temiz taban gerekti.

## Kural

- **Liste (`NER_NOISE_STOPWORDS`):** MUHAFAZAKÂR — yalnız asla named-entity (kişi/kurum/yer/olay)
  olmayan NET function/generic kelimeler: varlık/durum fiilleri (var, yok, olur, oldu, olmuş,
  olacak), zaman (bugün, dün, yarın, zaman, şimdi), jenerik isimler (bilgi, durum, şey, konu,
  haber, açıklama, sonuç).
- **Belirsizler KASITLA dışarıda:** küba (yer), borsa, elektrik, gram, alan, ece, politico —
  legit olabilir; yanlış-eleme = veri kaybı.
- **`is_noise_entity`:** `_fold` (lower + TR→ASCII + combining-mark strip + alnum-only) ile
  eşleştirir → "Bugün"/"BUGÜN"/"bugün" + "BİLGİ" (combining-dot) hepsi yakalanır. Type-agnostik
  (bu kelimeler hiçbir tipte geçerli ad değil).

## İki kullanım noktası

1. **NER ingest** (`entities.py`): `is_noise_entity(norm)` → skip + `skipped++`. Yeni
   makaleler gürültüsüz; `entities` tablosu SİLİNMEZ (RAG-kritik veri güvenliği — yalnız
   ingest-zamanı filtre).
2. **Küme çapası** (`select_canonical_anchor`): gate+tip+canonical sonrası `not is_noise_entity`
   → mevcut gürültü entity'si gate'i geçse bile çapa OLAMAZ → rebuild ile temiz küme.

## İlişkiler

- [[global-research-cluster-model]] — §Çapa seçimi; bu filtre çapa gate'inin son katmanı (#1598).
- [[clusters-trends-integration-2026-06]] — trend×küme ortak entity tabanı; bu filtre ikisini de besler.
- [[entity-canonicalization-faz1]] — canonical katman (gürültü değil, kimlik birleştirme — tamamlayıcı).
- [[trend-unit-entity-centered]] — trend entity birimi (aynı korpus).

## Kaynaklar

- `apps/api/app/core/entity_noise.py` — `NER_NOISE_STOPWORDS` + `is_noise_entity` + `_fold`.
- `apps/api/app/modules/entities/tasks/entities.py` §INSERT — NER ingest skip.
- `apps/api/app/core/research_clustering.py` §`select_canonical_anchor` — çapa-exclude.
- Test: `tests/unit/test_entity_noise.py` + `test_research_clustering.py` (noise-exclusion).
