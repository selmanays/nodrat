---
type: decision
title: "Sufficiency soft-gate — agenda yetersizse chunks-first fallback dene (#726)"
slug: "sufficiency-soft-gate"
status: "locked"
decided_on: "2026-05-12"
decided_by: "tech"
created: "2026-05-12"
updated: "2026-05-12"
sources:
  - "apps/api/app/api/app_generate.py §350-371"
  - "apps/api/app/api/app_generate_stream.py §317-338"
  - "apps/api/app/core/data_sufficiency.py"
  - "wiki/decisions/chunks-first-retrieval.md (PR #637)"
  - "wiki/decisions/chunks-always-on-fallback.md"
  - "GitHub Issue #726 / PR #729 / PR #732"
tags: ["locked-decision", "rag", "retrieval", "sufficiency", "soft-gate", "mvp-1-8"]
aliases: ["soft-gate", "sufficiency-fallback"]
---

# Sufficiency soft-gate — agenda yetersizse chunks-first fallback dene

> **Karar:** `check_sufficiency()` çağrısı korunur ama **erken çıkış kaldırılır**. Sonuç telemetri olarak loglanır + retrieval'a devam edilir. Gerçek "kaynak yok" kararı yalnız retrieval sonucundan verilir (agenda + chunks her ikisi de boş ise insufficient_data). Tüm modlar (current/weekly/archive/comparison) aynı davranır.
> **Durum:** locked
> **Tarih:** 2026-05-12 (#726/PR #729 ana fix, #732 warning persist follow-up).

## Bağlam — neden hard-gate yanıltıcıydı

#675'te sufficiency erken çıkışı archive/weekly/comparison modları için yumuşatılmıştı, ama `mode='current'` hala agenda_cards count'a bakıp 2'den azsa `insufficient_data` ile erken çıkıyordu. Bu, [[chunks-first-retrieval]] (PR #637) + [[chunks-always-on-fallback]] mimarisini bypass ediyordu.

Üretim semptomu (2026-05-12, kullanıcı raporu):

| Sorgu | Planner timeframe | Status |
|---|---|---|
| "afyon belediye başkanı **ne yaptı**" | son 1 hafta | ✅ completed |
| "afyon belediye başkanı **olayı nedir**" | bugün | ❌ insufficient_data |

İki sorgu aynı konu, aynı tarih, aynı kullanıcı — planner DeepSeek kelimeye duyarlı timeframe seçiyor → "olayı nedir" dar pencere "bugün" → o gün için 0 agenda card → hard-gate erken çıkış → kullanıcı boş yanıt görüyor.

**Çelişki:** RAG inceleyici (`/admin/rag/inspect-query`) aynı sorgudan sonuç buluyordu çünkü chunks-first retrieval 90 gün pencerede 11 May Burcu Köksal cards'ı yakalıyor. Yani **veri vardı**, sadece hard-gate okuma fırsatı vermiyordu.

## Karar mantığı

Üç prensip:

1. **Tek karar noktası:** "Kaynak yok" yalnız retrieval sonucundan verilmeli — count-based prediction'dan değil. Chunks-first always-on (90 gün penceresi, summary_emb + NER + IDF) zaten doğru fallback'i sağlıyor.

2. **Sufficiency telemetri olarak yararlı:** `check_sufficiency()` çağrısı korunur (cost ~5ms, sadece COUNT). Sonuç log'a yazılır + `_sufficiency_softfail` bayrağı set edilir. Pipeline hata ayıklaması ve cost analitiği için gerekli.

3. **Soft-fail transparancy:** Soft-fail tetiklendiğinde kullanıcıya warning gösterilir ("Planner timeframe penceresinde agenda card yetersizdi; geniş retrieval (chunks 90 gün) ile cevap üretildi."). DB row `generations.warnings` JSONB'sinde persist edilir.

## Alternatifler ve neden (red/kabul)

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Hard-gate (eski) — mode='current' early exit | Maliyet kontrolü | Chunks-first bypass; %15 sorgu boş yanıt | ❌ Reddedildi (#726) |
| Soft-gate + telemetri (yeni) | Chunks-first fırsat; warning transparan | +%0-15 content_generator call (önceden fail eden) | ✅ **Kabul edildi** |
| Tüm modlar hard-gate kaldır | En basit | Telemetri kaybı | Reddedildi (gözlemlenebilirlik gerek) |
| Planner timeframe genişlet (sadece #727) | Kelime duyarlılığını yumuşatır | DeepSeek hala kelime'ye direnebilir (kanıtlandı) | ✅ Tamamlayıcı (#727 — PR #730) |

## Sonuçlar

- **Etkilenen kavramlar:** [[chunks-first-retrieval]] (pekiştirildi), [[chunks-always-on-fallback]] (referans), [[ner-pipeline]] (Faz 7d extension)
- **Etkilenen kararlar:** [[entity-match-relevance]] (orthogonal), [[chunks-first-retrieval]] (uyumlu)
- **Etkilenen kod:**
  - `apps/api/app/api/app_generate.py:350-371` — sufficiency erken çıkış kaldırıldı, `_sufficiency_softfail` bayrağı; line ~702 soft-fail warning ekleme (reassignment, JSONB ORM gotcha #732)
  - `apps/api/app/api/app_generate_stream.py:317-338` — aynı pattern; line ~691 SSE 'progress' event (`stage='softgate_fallback'`); line ~1099 final warning persist
  - `apps/api/app/core/data_sufficiency.py` — sadece okuma, sözleşme değişmedi
- **Etkilenen dokümanlar:** [docs/engineering/architecture.md](../../docs/engineering/architecture.md) §retrieval pipeline (gelecek wiki ingest'te yansıt)

## Geri alma maliyeti

Bu karar değiştirilirse (hard-gate'e geri dönülürse):

1. Kod: tek if bloğu eklemek. `_sufficiency_softfail` durumunda `return insufficient_data` — küçük diff.
2. UX regression: önceden çalışan "olayı nedir" sorguları tekrar boş döner. Kullanıcı raporları beklenebilir.
3. Cost düşer: önceden fail eden sorguların content_generator çağrısı atlanır (~%0-15 call azalır).
4. Telemetri korunur: `_sufficiency_softfail` log'u zaten geliyor; geri alımda yorum hatası olabilir.

**Tahmini geri alım süresi:** 1 saat (kod) + 1-2 gün (rollout, log gözlem).

## İlişkiler

- **Bağlı kavramlar:** [[chunks-first-retrieval]] (mimari öncülü), [[chunks-always-on-fallback]] (uyumlu fallback davranışı), [[ner-pipeline]] (Faz 7d sertleştirme katmanı)
- **Bağlı topics:** [[pipeline-performance-baseline]]
- **İlgili kararlar:** [[entity-match-relevance]]
- **Bağlı sayfalar:** [[planner-cache]] (planner istemi #727 ile yumuşatılır)

## Kaynaklar

- [Issue #726](https://github.com/selmanays/nodrat/issues/726) — Ana sorun
- [PR #729](https://github.com/selmanays/nodrat/pull/729) — Soft-gate fix
- [PR #732](https://github.com/selmanays/nodrat/pull/732) — Warning persist follow-up
- [apps/api/app/api/app_generate.py](../../apps/api/app/api/app_generate.py) §350-371 §702
- [apps/api/app/api/app_generate_stream.py](../../apps/api/app/api/app_generate_stream.py) §317-338 §691 §1099
