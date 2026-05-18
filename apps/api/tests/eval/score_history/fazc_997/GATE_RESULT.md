# #927 Faz-C — Wikidata-alias entity genişletme · GATE RESULT (NEGATİF SPIKE)

**Tarih:** 2026-05-18 · **Issue:** #997 · **Branch:** `fix/997-wikidata-alias-expansion`
**Deploy:** VPS prod-parity (origin/main 95fb616 + Faz-C; api+worker_rag rebuild),
benchmark `niche_chunks_benchmark_v2` (planner→HyDE→multi-query→hybrid_search RRF).

> **Not (audit izi):** `--output /tmp/*.json` api CONTAINER-içi yazıyor; flag-reset
> için yapılan `docker compose restart api` container /tmp'sini sildi → JSON
> dosyaları kayboldu. Aşağıdaki tablolar **koşum stdout'undan birebir** transkript
> (4 koşumun per-query rank + summary'si canlı gözlemlendi). Süreç dersi: benchmark
> artifact'ı container'dan `docker compose cp` ile restart ÖNCESİ çek.

## Özet (gate)

| Metric | flag-OFF ×2 median | flag-ON ×2 median | Δ | Gate |
|---|---|---|---|---|
| recall@5 | **0.727** | **0.727** | 0.000 | = (regresyon yok; upside yok) |
| recall@10 | **0.818** | **0.818** | 0.000 | = (regresyon yok; upside yok) |
| NF (top-10) | {niche_007, niche_009} | {niche_007, niche_009} | değişmedi | — |
| avg_latency | ~47.8s (off_1) | 45.0s (on_1) / 41.9s (on_2) | ≤0 | latency-gate ✓ |

**Karar:** `recall@5_ON ≥ recall@5_OFF` ✓ ve `recall@10_ON ≥ recall@10_OFF` ✓
(regresyon kapısı PASS — kod güvenli, kanıtlanabilir no-op). **ANCAK** issue
#997 spike kapısı "recall ARTAR → default ON; aksi → flag-OFF dökümante".
**Recall ARTMADI (Δ=0.000) → NEGATİF SPIKE → flag default OFF kalır + ders.**
Median-of-3'te 2/2 koşum birebir (0.727/0.818) → 3. koşum matematiksel gereksiz.

## Per-query rank

| query | ce (planner) | OFF#1 | OFF#2 | ON#1 | ON#2 |
|---|---|---|---|---|---|
| niche_001 | karşıyaka,bursaspor,hakem | #1 | #1 | #1 | #1 |
| niche_002 | karşıyaka,bursaspor | #5 | #4 | (≤5) | #3 |
| niche_003 | trump,truth social | #2 | #5 | #4 | #4 |
| niche_004 | surp giragos,(diyarbakır/ermeni kilisesi) | #1 | #2 | #2 | #1 |
| niche_005 | fatih tutak | #2 | #2 | #2 | #2 |
| niche_006 | rodos devleti | #1 | #1 | #1 | #1 |
| niche_007 | hürmüz boğazı,abd | **NF** | **NF** | **NF** | **NF** |
| niche_008 | hürmüz boğazı | #6 | #8 | #7 | #8 |
| niche_009 | 15 temmuz,mağdur | **NF** | **NF** | **NF** | **NF** |
| niche_010 | emine aydınbelge | #1 | #1 | #1 | #1 |
| niche_011 | sovyet birliği,terk edildi | #1 | #5 | #4 | #4 |
| **recall@5 / @10** | | 0.727/0.818 | 0.727/0.818 | 0.727/0.818 | 0.727/0.818 |

(OFF#1 mrr=0.579, OFF#2 mrr=0.434, ON#1 mrr=0.445, ON#2 mrr=0.496 — HyDE
temp=0.7 gürültüsü; rank pozisyonları oynuyor ama 8/11@5 + 9/11@10 + NF set
4/4 koşumda STABİL.)

## Kök-neden (flag-ON çözülen entity_synonyms dökümü — neden upside yok)

Wikidata alias'ları **doğru kablolandı ve çözüldü** (mekanizma çalışıyor):
- niche_007 `abd` → `[Amerika Birleşik Devletleri, United States, Amerika,
  A.B.D., Birleşik Devletler, BD, ...]` (DOĞRU), `hürmüz boğazı` →
  `[Strait of Hormuz, ...]`. Yine NF. Golden failure_reason: "LLM yanlış
  paragraf seçimi / single-chunk 282-token" — sorun **substring-miss DEĞİL**;
  entity zaten bulunabilir, makale RRF top-15'e dense+sparse ile girmiyor.
  Eş-ad eklemek RRF sıralamasını bu 1-chunk makaleyi yüzeye çıkaracak kadar
  değiştirmiyor.
- niche_009 `15 temmuz` → `[July 15, July 15th, 15th of July, 15 July,
  Jul 15]` — **Wikidata YANLIŞ-ANLAM**: çıplak "15 temmuz" string'i takvim
  günü Q-ID'sine eşleşti ("2016 Türkiye askerî darbe girişimi" DEĞİL) →
  İngilizce takvim gürültüsü. `mağdur` → `[victim, kurban, müşteki, victims]`
  (jenerik). Hedef darbe-mağduru-röportajı makalesini bulmaya yardımı yok.

**Genel ders:** Çıplak Türkçe haber-olay keyword'ü → Wikidata QID
disambiguation **güvenilmez** (wbsearchentities ilk-sonuç ≠ haber-bağlamı
entity'si). Eş-ad genişletme niş-recall'u ancak hata gerçekten eş-ad-substring
miss ise yardımcı olur; golden_set'in 2 NF vakası farklı kök-nedene sahip
(answer-extraction/ranking + yanlış-anlam-QID). #842/#863/#967/#970/#973
Wikipedia-bilgi-yolu zaten ana eş-ad ihtiyacını chat tarafında karşılıyor.

## Sonuç

Kod **doğru, güvenli, kanıtlanabilir no-op** (flag-OFF ×2 == baseline
0.727/0.818; 14 unit + 175 komşu regression pass). Foundation
(`wikidata_aliases` + `entity_synonyms` plumbing + flag) korunur ama
**default OFF** — gelecekte daha iyi entity→QID disambiguation ile yeniden
denenebilir (çıplak-keyword yerine #863/#967 kanonik-sayfa QID'si besle).
Dürüst negatif: `wiki/topics/failed-experiments-rag-quality.md` (Faz-B #5'in
yanına Faz-C #6).
