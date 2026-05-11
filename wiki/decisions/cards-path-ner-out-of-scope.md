---
type: decision
title: "Cards path'e NER stream eklemek — Out of Scope (MVP-1.8)"
slug: "cards-path-ner-out-of-scope"
category: "rag"
status: "locked"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "apps/api/app/core/retrieval.py (hybrid_search_agenda_cards — NER yok; hybrid_search_chunks — NER var)"
  - "apps/api/tests/eval/golden_sets/retrieval_golden_tr.yaml (55 sorgu, agenda-focused)"
  - "GitHub Issue #696 Faz E20 — formal karar"
tags: ["rag", "ner", "cards", "decision", "out-of-scope", "mvp-1-8"]
---

# Cards Path'e NER Stream Eklemek — Out of Scope

> **TL;DR:** Admin benchmark "cards" suite'inde NDCG@10 0.07 görünür, "chunks" suite'inde 0.49. Cards path NER yok; chunks path NER var. **Cards path'e NER eklemek MVP-1.8'de planlanmıyor** — sebep: agenda card retrieval amacı farklı (öne çıkan haber kartı), niş entity bu seviyede beklenmez. Production /api/generate kullanıcı yolu chunks path → kullanıcı çıktıları zaten iyi. Cards seviyesinde NER yatırımının ROI'si düşük.

## Karar Bağlamı (#696 audit sonrası)

Sprint #696 audit'inde tespit edildi: iki retrieval path var.

| Path | Fonksiyon | Amaç | NER? |
|---|---|---|---|
| **cards** | `hybrid_search_agenda_cards` | Daily/weekly agenda card retrieval (homepage trending) | ❌ |
| **chunks** | `hybrid_search_chunks` | Article chunk retrieval (kullanıcı /generate) | ✅ |

Admin benchmark eski default cards path → niş entity sorguları NER'siz başarısız → NDCG@10 0.07.

PR #697 (Faz A) sonrası benchmark default chunks → NDCG@10 0.49 (6x iyileşme), Faz 6.1 hedefi tutturuldu.

## Sorulan Soru

**Cards path'e de NER eklemek mantıklı mı?**

## Cevap — HAYIR (locked decision)

### 1. Cards amacı farklı

- **agenda_cards** = LLM tarafından üretilen "öne çıkan günlük haber kartı"
- İçerik: title + summary + key_points + content_angles + timeline (1-3 paragraf)
- Kullanım: homepage trending, kategori bazlı agenda
- Sorgu örnekleri: "1 Mayıs bankalar açık mı", "altın fiyatları bugün", "günün önemli haberleri"

Niş entity sorguları (Karşıyaka maç skoru, Fatih Tutak son işler) cards seviyesinde beklenmez — bunlar **article chunks** seviyesinde semantic match gerektirir.

### 2. Golden set 50→55 analizi (#696 E19)

Yeni 5 sorgu (#245 e4eb3a2):
- q_051: İstanbul su kesintisi (agenda)
- q_052: BEDAŞ elektrik kesintisi (agenda)
- q_053: altın fiyatları bugün (agenda)
- q_054: gram altın çeyrek altın (agenda)
- q_055: günün önemli haberleri (agenda multi-card)

Hiçbiri niş entity DEĞİL. Cards path bu sorgularda zaten **uygun olmalı**. Eski yüksek NDCG (0.85, 3-6 Mayıs) cards path'in bu sorgu setinde iyi performansını gösteriyordu.

### 3. NER backfill scale etkisi cards'i de bozar mıydı?

Eğer cards path NER ile entegre olsaydı, [[ner-pipeline]] §Faz 6.1'de açıklanan **scale dilution** problemi cards seviyesinde de yaşanırdı. ILIKE `%X%` cap'i 20+ card match → sinyal sulanır.

Yani cards'a NER eklemek **çift dert** olurdu:
- Karmaşık IDF logic gerek (chunks ile aynı)
- Cards corpus zaten daha küçük (~yüzlerce daily card), df threshold ayarı daha zor
- Agenda card semantics (LLM-generated summary) zaten "öne çıkan" filtreyi yapıyor; raw entity match'e ihtiyaç düşük

### 4. Production kanıt

`/api/generate` chunks path kullanıyor, NER aktif. Kullanıcılar son hafta gözlemlenen iyileşmeyi (Karşıyaka basketbol article'ı Fatih Tutak) gerçek deneyim ediyor. Cards path eski yüksek NDCG (0.85) bozulması admin metrik UI'da görünür ama prod akış etkilenmedi.

## Alternatifler (yapmadık)

| Opsiyon | Tarif | Reddedildi sebep |
|---|---|---|
| A. Cards'a aynı IDF+multi-entity AND stream'i ekle | hybrid_search_agenda_cards içine `_ner_idf_match_aids` ekle | ROI düşük; cards amacı farklı |
| B. Cards golden set'i niş sorgulardan arındır | retrieval_golden_tr'den niş entity sorgularını çıkar | Test set fakirleşir; iki suite ayrımı zaten çözüm |
| C. Cards retrieval'de RRF K=30 NER stream sentetik ekle | Cards article_ids'lerinden Faz 6 sentetik boost | Implementation karmaşık; kazanç belirsiz |

## Re-evaluation tetikleyicileri

Aşağıdaki koşullardan biri olursa karar yeniden gözden geçirilir:

1. Production telemetri: cards path kullanan endpoint (varsa) niş entity sorgularda fail oranı yüksek
2. UX feedback: kullanıcı agenda chip'lerinde niş entity haber kartı arıyor (örn. "Karşıyaka basketbol" diye ana sayfada arama)
3. Cards golden set 100+ sorguya çıkarsa ve niş entity oranı artarsa
4. NER pipeline'ın scale etkisi (df threshold tuning) için generalized solution çıkarsa

## İlişkiler

- [[eval-benchmark-divergence]] — cards vs chunks path divergence detay
- [[idf-entity-weighting]] — chunks path NER scoring overhaul
- [[ner-pipeline]] — Faz 6/6.1 NER implementation chunks-only

## Kaynaklar

- [Issue #696](https://github.com/selmanays/nodrat/issues/696) — audit epic, Faz E20
- [PR #697](https://github.com/selmanays/nodrat/pull/697) — admin benchmark suite param fix
- [PR #693](https://github.com/selmanays/nodrat/pull/693) — Faz 6.1 NER scoring overhaul (chunks-only)
