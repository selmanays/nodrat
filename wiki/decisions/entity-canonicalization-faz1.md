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
  - "apps/api/app/api/admin_entities.py"
  - "docs/engineering/data-model.md§6.1b"
  - "docs/engineering/api-contracts.md§6b"
tags: [entities, trends, canonicalization, decision, gundem, locked]
aliases: ["entity alias", "canonical entity", "varyant birleştirme", "CHP Cumhuriyet Halk Partisi"]
---

# Entity Canonicalization — varyant birleştirme (Faz 1)

## TL;DR

Aynı varlığın farklı yüzey biçimleri (CHP↔Cumhuriyet Halk Partisi · Cumhurbaşkanı Erdoğan↔Recep Tayyip Erdoğan · Trump↔Donald Trump) trend listesinde ayrı gruplanıyordu → **canonical kimlik katmanı** eklendi (#1540). **`entities` tablosu dokunulmaz** (orijinal biçimler korunur); üstüne `entity_aliases`→`canonical_entities` eşlemesi konur, trend okuması (flag ON) canonical bazında gruplar. Faz 1 = **deterministik** (LLM-siz): küratörlü seed + person unvan-soyma + ilk-ad guard + **token-altküme merge** (#1548, event; "2026 FIFA Dünya Kupası"↔"2026 Dünya Kupası") + **admin merge/split** (#1554, belirsiz vakalar için elle, builder ezmez). Prod doğrulandı: Erdoğan 6+ parça→tek 131 haber, CHP 124+17→130; token-subset 386 eşleşme/148 event grubu.

## Problem (prod kanıtı)

`entity_normalized` yalnız `lower + strip_quote` yapıyordu → varyantlar parçalanıyordu. Son 7g'de tek kişi (Erdoğan) ≥6 ayrı entity'ye bölünmüştü ("recep tayyip erdoğan" 73, "cumhurbaşkanı erdoğan" 32, "cumhurbaşkanı recep tayyip erdoğan" 32, "erdoğan" 15…); CHP de "chp" (124) + "cumhuriyet halk partisi" (17) ayrı. Trend `entity_normalized` bazında gruplayınca hacim bölünüyor → gerçek lider trend görünmüyordu. 85.228 distinct entity_normalized.

## Karar (LOCKED)

1. **Additive canonical katman:** `canonical_entities` (canonical_name/entity_type/canonical_normalized) + `entity_aliases` (alias_normalized,entity_type→canonical_id). `entities` **okunur, yazılmaz**. Şema: data-model §6.1b. Raw-SQL-only (alembic allowlist). Migration `20260616_0100`.
2. **Faz 1 = deterministik resolution** (`canonicalization.py`, saf/test-edilebilir):
   - **Küratörlü seed** (~30 grup): top TR kişi/org. Org **akronim↔açık ad** (CHP↔Cumhuriyet Halk Partisi, AKP↔AK Parti, TCMB↔Merkez Bankası) burada çözülür — kural ile türetilemez.
   - **Person unvan-soyma:** "Cumhurbaşkanı Erdoğan" → "erdoğan" → seed. ("akpli cumhurbaşkanı erdoğan", "başkan trump" de yakalanır.)
   - **İlk-ad çakışma guard:** "emine erdoğan"/"bilal erdoğan" seed'de yok + unvan-ön-ek yok → **birleştirilmez** (farklı kişi tuzağı). Konservatif: riskli generic soyad-merge YAPILMAZ.
   - **Token-altküme birleştirme** (#1548/#1549, yalnız `event` tipi, `canonicalization.build_subset_groups`): seed/spesifik-örnek YOK, tamamen jenerik. "2026 fifa dünya kupası" / "fifa dünya kupası" / "2026 dünya kupası" gibi varyantlar → union-find ile (1) eşit token-kümesi merge + (2) **tek minimal üst-küme** merge. Canonical = en sık üye (eşitlik→en uzun); ≥2 token şartı. Belirsiz vaka (örn. "2026 dünya kupası" hem FIFA hem "2026 okçuluk dünya kupası" alt-kümesi olabilir → birden çok üst-küme) **birleştirilmez** → admin'e bırakılır (madde 6). `source='token_subset'`, confidence 0.900.
3. **Builder:** `tasks.entities.build_canonical` (beat 6sa + admin trigger) entities tarar → seed/unvan + token-altküme eşleşmelerini idempotent upsert. ner_queue→worker_ner. **Admin override koruması:** alias upsert `ON CONFLICT DO UPDATE ... WHERE entity_aliases.source <> 'admin'` → yeniden çalışan builder, admin'in elle verdiği kararı (madde 6) **EZMEZ**.
4. **Trend read (flag-gated):** `trends.canonical_entities.enabled` (default OFF) ON iken `_read_entity_trends` alias JOIN ile `canonical_normalized` grup anahtarı + label=`canonical_name` (agg + sparkline). Eşleşmeyen entity ham kalır.
5. **Admin merge/split** (#1554, `app/api/admin_entities.py`, prefix `/admin/entities`): deterministik builder'ın çözemediği belirsiz vakaları admin elle yönetir → **birleştir** (kaynak canonical'ın alias'larını hedefe taşı + kaynağı sil) · **ayır/split** (varyant eşlemesini kaldır) · **manuel alias ekle** · **yeni canonical**. Hepsi `require_admin` + `AdminAuditLog`; tüm admin mutation'ları `source='admin'` ile işaretlenir (madde 3 koruması). FE: `/admin/entities/canonical` yönetim sayfası (liste + detay diyalog + birleştirme adayları). Bu, belirsiz token-altküme vakalarının (örn. "2026 Dünya Kupası"→FIFA) **insan-onaylı** çözüm yoludur — LLM gerektirmez.

## Alternatifler (değerlendirildi)

- **NER-zamanı canonicalization:** NER prompt'una canonical döndürtmek — reddedildi (NER tek makale görür, global canonical kümeyi bilmez; tutarsız).
- **Generic soyad/embedding auto-merge:** reddedildi (Emine/Bilal Erdoğan yanlış birleşir) → Faz 2'de LLM + admin review ile.

## Bilinen sınırlama / Faz 2

- Faz 1 = seed + unvan-soyma + token-altküme (event) → **uzun kuyruk** (seed dışı binlerce entity, alternatif adlar, kurum varyantları) otomatik kapsanmaz; ama artık **admin merge/split** (madde 5) ile elle çözülebilir + builder bu kararları ezmez.
- **Faz 2 (deferred):** LLM-destekli toplu canonicalization (top-volume distinct entity → DeepSeek cluster) + initialism aday üreteci → admin'e **öneri** olarak sunulur (admin merge/split UI zaten hazır).
- Akronim belirsizliği (kısa 2-harf) → seed'e konservatif alındı; geri kalanı admin'e.
- Token-altküme **frequency-dominance tie-breaker** (örn. "2026 dünya kupası" hacim baskınlığıyla otomatik FIFA'ya) değerlendirildi ama **admin merge** daha doğru cevap olduğu için ertelendi.

## İlişkiler

- [[trend-intelligence-admin-overview-2026-06]] — entity-merkezli trend; canonical bu listeyi gruplar + admin merge/split + detail drill-down aynı admin yüzeyinde.
- [[trend-unit-entity-centered]] — entity trend birimi kararı (bu kararın üstüne kurulur).
- [[admin-route-domain-ownership]] — `/admin/entities` route'unun aggregator (`app/api/`) yerleşimi.

## Kaynaklar

- [data-model.md §6.1b](../../docs/engineering/data-model.md) — canonical_entities + entity_aliases şema.
- [api-contracts.md §6b](../../docs/engineering/api-contracts.md) — `trends.canonical_entities.enabled` + `/admin/entities` davranışı.
- Kod: `app/modules/entities/canonicalization.py` (seed + unvan-soyma + guard + `build_subset_groups`) · `tasks/canonical.py` (builder + admin-override guard) · `app/api/admin_entities.py` (merge/split/alias).
- Test: `tests/migration/test_canonical_admin_invariants.py` (builder admin-alias ezmez + merge/split SQL invariant, CI testcontainers) · `tests/unit/test_admin_entities.py` (router wiring) · `tests/unit/test_canonicalization.py` (resolver).
- PR: token-altküme [#1549](https://github.com/selmanays/nodrat/pull/1549) (#1548) · admin merge/split [#1555](https://github.com/selmanays/nodrat/pull/1555) (#1554).
