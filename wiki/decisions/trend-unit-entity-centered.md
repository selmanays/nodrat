---
type: decision
title: "Trend birimi = ENTITY (cluster/topic değil) — entity-merkezli trend radarı"
slug: "trend-unit-entity-centered"
status: live
created: 2026-06-15
updated: 2026-06-15
sources:
  - "apps/api/app/api/admin_trends.py"
  - "apps/api/app/modules/trends/aggregation.py"
  - "docs/engineering/api-contracts.md§6b"
  - "docs/engineering/data-model.md§13c"
tags: [trends, decision, entity, gundem, locked]
aliases: ["entity-centered trend", "entity trend birimi", "trend headline problemi"]
---

# Trend birimi = ENTITY (cluster/topic değil)

## TL;DR

Trend Intelligence'ın ölçüm birimi **entity** (kişi/kurum/yer/olay) olarak **kilitlendi** (#1518). Cluster/topic-tabanlı eski yol "ham haber başlığı trendi" ürettiği için **#1520 ile tamamen kaldırıldı** (entity tek okuma yolu). Karar prod kanıtına dayanır: aynı pencerede cluster yolu **24s'te 0** anlamlı sonuç verirken entity yolu **24s'te ~279** gated entity üretir. Bkz. [[trend-intelligence-admin-overview-2026-06]].

## Problem — neden cluster/topic birim başarısız oldu

Faz 1 (#1500) cluster-tabanlı, Faz 2 (#1505) kalıcı `topics` birimi kurdu. Ama:

- **`topics.label = event_clusters.canonical_title = articles.title`** → "konu" diye gösterilen şey **ilk haberin ham SEO başlığı** (HTML entity'leri bile decode edilmemiş, örn. `&#039;`).
- **event_clusters ~%93 singleton:** prod ölçümü — 6s'te bir cluster'da en fazla 1 haber, 24s'te 2, **7g'de bile en fazla 2**. Cluster anlamlı trend birimi olamaz.
- **Evidence gate yoktu** → `article_count=0` satırlar listede; tek haberle "Patlıyor" (`prev=0 → breaking`).

Sonuç: sistem **"gündem/olay/entity trendi" yerine tekil haber başlığı trendi** yapıyordu.

## Karar (LOCKED)

1. **Trend birimi = entity.** `entities ⋈ articles` üzerinden `entity_normalized + entity_type` (person|org|place|event) bazında agregasyon. Label = `mode() entity_text` (en sık yüzey biçim — "Türkiye", "Donald Trump"), ham başlık değil.
2. **Ölçüm yayın zamanına göre** (`articles.published_at`) — kazıma/işleme zamanına göre değil.
3. **Evidence gate** (runtime tunable): pencerede ≥`trends.gate.min_articles`(2) haber **ve** ≥`trends.gate.min_sources`(2) distinct kaynak. Tek haber asla "breaking" değil (`prev=0` iken breaking yalnız `cur≥3`).
4. **Birleşik skor** (varsayılan sıralama): `0.40·volume + 0.25·momentum + 0.20·source_diversity + 0.10·recency + 0.05·reliability`. Volume + momentum + kaynak çeşitliliği birincil. **Novelty skora girmez** — yalnız tie-breaker.
5. **Cluster/snapshot okuma yolu kaldırıldı** (#1520) — `subject` param, `_read_topic_trends`, canlı cluster SQL repodan silindi. Entity tek okuma yolu.

## Alternatifler (değerlendirildi, reddedildi)

- **Gated event_cluster + agenda label:** çok-haberli cluster + agenda_card başlığı. Reddedildi — %93 singleton yüzünden liste seyrek/boş kalır.
- **Cluster path'i debug için tutmak:** kısa süre `subject=cluster` debug toggle olarak tutuldu, doğrulama sonrası kaldırıldı (kafa karıştırıcı + layout bug).

## Bilinen sınırlama / açık sorular

- **Jenerik baskınlık:** yer entity'leri (ülke/şehir) hacimde baskın → liste "place" tipiyle dolabilir (top20'nin ~19'u place; tek person Donald Trump). Çözüm önerisi (sonraki PR): tunable generic-entity stoplist VEYA place-type down-weight VEYA momentum-sort. Bu PR'da kasıtlı ertelendi.
- **Persistence:** kalıcı entity snapshot (zaman-serisi) henüz yok; mevcut `trend_snapshots` tabloları topic-tabanlı + dormant (worker OFF). İleri faz: entity snapshot persistence.

## İlişkiler

- [[trend-intelligence-admin-overview-2026-06]] — endpoint + pipeline + deploy detayları (bu kararın uygulandığı topic).
- [[data-pipelines]] — entities (NER) + clustering substratı.

## Kaynaklar

- [api-contracts.md §6b](../../docs/engineering/api-contracts.md) — `GET /admin/trends` entity-merkezli sözleşme.
- [data-model.md §13c](../../docs/engineering/data-model.md) — dormant trend persistence şeması.
- Kod: `apps/api/app/api/admin_trends.py` (`_read_entity_trends`), `apps/api/app/modules/trends/aggregation.py` (`compute_trend_score`).
