---
type: decision
title: "Entity Canonicalization — varyant birleştirme (Faz 1: deterministik seed + unvan-soyma)"
slug: "entity-canonicalization-faz1"
status: live
created: 2026-06-16
updated: 2026-06-16
sources:
  - "apps/api/app/modules/entities/canonicalization.py"
  - "apps/api/app/modules/entities/tasks/canonical.py"
  - "docs/engineering/data-model.md§6.1b"
  - "docs/engineering/api-contracts.md§6b"
tags: [entities, trends, canonicalization, decision, gundem, locked]
aliases: ["entity alias", "canonical entity", "varyant birleştirme", "CHP Cumhuriyet Halk Partisi"]
---

# Entity Canonicalization — varyant birleştirme (Faz 1)

## TL;DR

Aynı varlığın farklı yüzey biçimleri (CHP↔Cumhuriyet Halk Partisi · Cumhurbaşkanı Erdoğan↔Recep Tayyip Erdoğan · Trump↔Donald Trump) trend listesinde ayrı gruplanıyordu → **canonical kimlik katmanı** eklendi (#1540). **`entities` tablosu dokunulmaz** (orijinal biçimler korunur); üstüne `entity_aliases`→`canonical_entities` eşlemesi konur, trend okuması (flag ON) canonical bazında gruplar. Faz 1 = **deterministik**: küratörlü seed + person unvan-soyma + ilk-ad guard. Prod doğrulandı: Erdoğan 6+ parça→tek 131 haber, CHP 124+17→130.

## Problem (prod kanıtı)

`entity_normalized` yalnız `lower + strip_quote` yapıyordu → varyantlar parçalanıyordu. Son 7g'de tek kişi (Erdoğan) ≥6 ayrı entity'ye bölünmüştü ("recep tayyip erdoğan" 73, "cumhurbaşkanı erdoğan" 32, "cumhurbaşkanı recep tayyip erdoğan" 32, "erdoğan" 15…); CHP de "chp" (124) + "cumhuriyet halk partisi" (17) ayrı. Trend `entity_normalized` bazında gruplayınca hacim bölünüyor → gerçek lider trend görünmüyordu. 85.228 distinct entity_normalized.

## Karar (LOCKED)

1. **Additive canonical katman:** `canonical_entities` (canonical_name/entity_type/canonical_normalized) + `entity_aliases` (alias_normalized,entity_type→canonical_id). `entities` **okunur, yazılmaz**. Şema: data-model §6.1b. Raw-SQL-only (alembic allowlist). Migration `20260616_0100`.
2. **Faz 1 = deterministik resolution** (`canonicalization.py`, saf/test-edilebilir):
   - **Küratörlü seed** (~30 grup): top TR kişi/org. Org **akronim↔açık ad** (CHP↔Cumhuriyet Halk Partisi, AKP↔AK Parti, TCMB↔Merkez Bankası) burada çözülür — kural ile türetilemez.
   - **Person unvan-soyma:** "Cumhurbaşkanı Erdoğan" → "erdoğan" → seed. ("akpli cumhurbaşkanı erdoğan", "başkan trump" de yakalanır.)
   - **İlk-ad çakışma guard:** "emine erdoğan"/"bilal erdoğan" seed'de yok + unvan-ön-ek yok → **birleştirilmez** (farklı kişi tuzağı). Konservatif: riskli generic soyad-merge YAPILMAZ.
3. **Builder:** `tasks.entities.build_canonical` (beat 6sa + admin trigger) entities tarar → seed/unvan eşleşmelerini idempotent upsert. ner_queue→worker_ner.
4. **Trend read (flag-gated):** `trends.canonical_entities.enabled` (default OFF) ON iken `_read_entity_trends` alias JOIN ile `canonical_normalized` grup anahtarı + label=`canonical_name` (agg + sparkline). Eşleşmeyen entity ham kalır.

## Alternatifler (değerlendirildi)

- **NER-zamanı canonicalization:** NER prompt'una canonical döndürtmek — reddedildi (NER tek makale görür, global canonical kümeyi bilmez; tutarsız).
- **Generic soyad/embedding auto-merge:** reddedildi (Emine/Bilal Erdoğan yanlış birleşir) → Faz 2'de LLM + admin review ile.

## Bilinen sınırlama / Faz 2

- Faz 1 yalnız seed + unvan-soyma → **uzun kuyruk** (seed dışı binlerce entity, alternatif adlar, kurum varyantları) kapsanmaz. **Faz 2:** LLM-destekli toplu canonicalization (top-volume distinct entity → DeepSeek cluster) + admin merge review + initialism aday üreteci.
- Akronim belirsizliği (kısa 2-harf) → seed'e konservatif alındı.

## İlişkiler

- [[trend-intelligence-admin-overview-2026-06]] — entity-merkezli trend; canonical bu listeyi gruplar.
- [[trend-unit-entity-centered]] — entity trend birimi kararı (bu kararın üstüne kurulur).

## Kaynaklar

- [data-model.md §6.1b](../../docs/engineering/data-model.md) — canonical_entities + entity_aliases şema.
- [api-contracts.md §6b](../../docs/engineering/api-contracts.md) — `trends.canonical_entities.enabled` davranışı.
- Kod: `app/modules/entities/canonicalization.py` (seed + unvan-soyma + guard) · `tasks/canonical.py` (builder).
