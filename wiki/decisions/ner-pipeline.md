---
type: decision
title: "NER pipeline — niş entity recall sıçraması (#667 Faz 6)"
slug: "ner-pipeline"
category: "rag"
status: "live"
created: "2026-05-11"
updated: "2026-05-12 (#720 — NER prompt prompts_store override edilebilir)"
sources:
  - "apps/api/app/prompts/ner.py (#720 — DeepSeek NER system prompt modülü)"
  - "apps/api/app/workers/tasks/entities.py (DeepSeek extraction worker)"
  - "apps/api/alembic/versions/20260511_0200_entities_table.py (migration)"
  - "apps/api/app/core/retrieval.py (NER stream RRF + IDF/multi-entity AND)"
  - "apps/api/app/core/rerank.py (_extract_entity_candidates apostrof fix)"
  - "GitHub Issue #667 / PR #668 / Issue #691 / PR #693 / Issue #720"
tags: ["rag", "ner", "retrieval", "entity-extraction", "mvp-1-8"]
aliases: ["faz6", "named-entity-recognition"]
---

# NER Pipeline

> **TL;DR:** Faz 5 sonrası bge-m3 Türkçe niş entity semantic match sınırına takıldık (recall@5 stable %45.5). NER pipeline ile cap'li özel adları (kişi/yer/kurum/etkinlik) entities tablosunda exact match → embedding bypass → **recall@5: 45.5% → 63.6%**, recall@10: 45.5% → 81.8%.

## Bağlam — bge-m3 ceiling

Faz 1-5 mimari tamamlandı (smart-quote, semantic chunker, multi-query, HyDE, parent-doc, summary embedding, LLM rerank). Niş entity için recall@5 stable %45.5. Tabandaki sorun:

- bge-m3 multilingual embedding Türkçe için kalibre değil
- Niş bilgi (hakem isimleri, % rakamı, kişi sözü) article ortasında bir cümlede
- Sorgu vector'ü ile article ana tema vector'ü arasında cosine sim 0.40-0.55 → threshold 0.65 altı drop

Karşıyaka basketbol article'ı (hakemler) ve Fatih Tutak (kişi adı) bu sebeple top-15'e bile giremiyordu.

## Çözüm — NER + exact match

LLM tabanlı (DeepSeek) entity extraction → entities tablosu → sorgu içindeki cap'li token'lar **exact match** → ilgili article'lar RRF'e EN GÜÇLÜ stream (K=30).

### Migration (20260511_0200)

```sql
CREATE TABLE entities (
  id uuid PRIMARY KEY,
  article_id uuid REFERENCES articles(id) ON DELETE CASCADE,
  entity_text varchar(200),
  entity_normalized varchar(200),      -- lower + strip_quote_variants
  entity_type varchar(20),             -- person/place/org/event/money/number/misc
  mention_count int,
  first_position varchar(20),          -- title/subtitle/body
  created_at timestamptz
);
CREATE INDEX idx_entities_normalized ON entities (entity_normalized, entity_type);
CREATE INDEX idx_entities_article ON entities (article_id);
CREATE INDEX idx_entities_normalized_trgm ON entities USING gin (entity_normalized gin_trgm_ops);
UNIQUE (article_id, entity_normalized, entity_type);
```

### Extraction worker

`tasks.entities.extract_article_entities` — DeepSeek V4 Flash json_mode:
- Input: title + subtitle + body[:3000]
- Output: 30 entity (kişi/yer/kurum/etkinlik/sayı)
- Cost: ~$0.0008/article (300-500 input + 100 output token)
- chunk_article zincirine eklendi → yeni article'lar otomatik NER

### Retrieval entegrasyonu

`hybrid_search_chunks` içine NER stream:
1. Query'den >=3 char entity adayı (mevcut `_extract_entity_candidates`)
2. `entities.entity_normalized ILIKE` search → matching article_id'ler
3. Bu article'ların ilk chunk'ları RRF'e priority stream (K_RRF=30 — sparse/dense üstü)
4. Parent-document retrieval ile article'ın diğer chunks'ları context'e

## Üretim sonucu — KAZANIM

> ⚠️ **Ölçüm koşulu:** Aşağıdaki Faz 6 skorları **NER backfill öncesi 9 test article entity'liyken** ölçüldü. Production'da backfill ile 4391 article entity'li hale geldiğinde bu kazanım sulandı (45.5%'e geri döndü); §Faz 6.1 (PR #693) IDF + multi-entity AND ile **63.6% scale-realistic** olarak geri kazanıldı (recall@10 72.7%). Detay: [[pipeline-optimization]].

| Metric | Pre-Faz | Faz 1-5 | **Faz 6 NER (9-article test)** | **Faz 6.1 (post-backfill scale-fix)** |
|---|---|---|---|---|
| recall@5 | 27.3% | 45.5% | 63.6% | **63.6%** ✅ |
| recall@10 | ~ | 45.5% | 81.8% | **72.7%** |
| Toplam kazanım | baseline | %66 | %133 göreceli (sentetik) | %133 göreceli (sürdürülebilir) |

### Yeni düzelenler (Faz 6 katkısı)

| Sorgu | Önce | Şimdi |
|---|---|---|
| Karşıyaka hakemler | ❌ NOT IN TOP-10 | ✅ #1 |
| Fatih Tutak son işler | ❌ NOT IN TOP-10 | ✅ |
| Karşıyaka skor | ❌ NOT IN TOP-10 | ✅ top-10 |
| 15 Temmuz röportaj | ❌ NOT IN TOP-10 | ✅ top-10 |

### Hala başarısız 3 vaka (top-5/10)

- Rodos kaç kent — numerical niş ("kaç ana kent" rakamı)
- ABD Hürmüz % — yüzde rakamı niş bilgi
- Karşıyaka skor top-5 değil (top-10) — Habertürk SEO başlıklar domine

## Trade-off

**Pro:**
- recall@5 sıçraması (+18 puan tek faz)
- recall@10 +36 puan
- Cap'li özel adlar (kişi/yer/kurum) embedding bypass
- Vakaya özel kod yok — herhangi entity için aynı kural
- chunk_article zincirine eklendi (yeni article'lar otomatik)

**Con:**
- Cost: ~$0.0008/article DeepSeek call (109K article × $87 bir kerelik)
- Latency +500-800ms entity extraction (background worker, kullanıcı görmez)
- LLM hallucination riski (DeepSeek var olmayan entity uydurursa) — mention_count filter ile mitigate

## Backfill stratejisi

- chunk_article zincirine eklendi → yeni article'lar otomatik
- `backfill_entities` task — eski 109K cleaned article için bulk dispatch
- Test article'ları öncelikli işlendi (9 article × 18 saniye = ~2.5 dk)

## Faz 6.1 — NER scoring overhaul (#691 / PR #693 — delivered)

### Sorun (post-backfill ölçüm)

Faz 6 ölçümü (45.5%→63.6%) sadece **9 article entity'liyken** yapıldı (test article'ları). NER backfill #684 PR-B ops ile 4391/4436 article entity'li hale geldi (%99 coverage, 69k entity row). Bu yeni ölçekte:

- Query "Karşıyaka" → `entity_normalized ILIKE '%karşıyaka%' LIMIT 20` cap'i dolu (semt, belediye, taciz, ESHOT, CHP, vs.)
- Her birine aynı K=30 RRF bonus → sinyal sulanıyor → doğru article sıralamada kayboluyor
- A/B (NER off) test: yine 5/11 → NER stream effective olarak ölü
- Sonuç: recall@5 **63.6% → 45.5%** (Faz 6 kazanımı silindi)

### Çözüm — IDF threshold + multi-entity AND (hibrit)

`_resolve_ner_target_aids` pure logic + `_ner_idf_match_aids` DB wrapper:

| Mode | Koşul | Boost K | Örnek |
|---|---|---|---|
| `multi_and` | 2+ rare entity (df<30) intersect dolu | K=20 (en güçlü) | "Karşıyaka + Bursaspor" |
| `multi_and_common` | Common entity AND intersect dar (<30) | K=20 | iki popüler entity'nin dar kesişimi |
| `single_rare` | Tek rare entity (df<30) | K=30 (Faz 6 eski) | "Aydınbelge" |
| `no_match` | Hiçbiri | yok | "Trump" tek başına |

### Yan iyileştirmeler

- **Stopword genişletme:** `maçı/kaç/bitti/nedir/işleri` Türkçe morpho/question kelime'leri NER token sayılmaz (niche_002 fix)
- **Apostrof fix:** `_extract_entity_candidates` apostrof'u SPACE'e çevirir → `Tutak'ın` → tokens `["tutak", "ın"]`, "ın" < min_len=3 dropped (niche_005 fix)
- **9 birim test:** Pure logic `_resolve_ner_target_aids` için empty/multi_and/single_rare/no_match/fallback/boundary/3-rare-intersect

### Ölçüm karşılaştırması (post-backfill, deterministic 3x)

| Metric | Pre-#684 baseline (Faz 6 ölçümü, 9-article entity) | Post backfill (#684) | v1 IDF only | **v2 final (#691)** |
|---|---|---|---|---|
| recall@5 | 63.6% (7/11) | 45.5% (5/11) | 54.5% (6/11) | **63.6% (7/11)** ✅ |
| recall@10 | 81.8% (9/11) | 45.5% (5/11) | 54.5% (6/11) | **72.7% (8/11)** |
| mrr@10 | - | 0.455 | 0.500 | **0.556** |
| avg_latency | ~14s | 14.7s | 15.2s | 16.0s |

**Faz 6 hedefi (63.6%) tam tutturuldu.** recall@10 Faz 6 ölçümünün altında (72.7% vs 81.8%) ama **sürdürülebilir** çünkü ölçek-dürüst.

### Düzelenler bu fazda

| Sorgu | Pre-#684 (Faz 6) | Post backfill | v2 (#691) |
|---|---|---|---|
| niche_001 Karşıyaka hakemler | ✅ | ❌ | ✅ #2 |
| niche_002 Karşıyaka skor | ✅ top-10 | ❌ | #9 (top-10) |
| niche_005 Fatih Tutak | ✅ | ❌ | ✅ #2 |

### Trade-off

**Pro:**
- ✅ Faz 6 kazanımı geri
- ✅ Backfill ölçeğine dayanıklı (scale-realistic)
- ✅ Latency neutral (+0.3s)
- ✅ Birim testler (9 case)

**Con:**
- Threshold (df=30) sabit, corpus büyüdükçe re-tune gerekebilir
- IDF formal değil (basit threshold) — ilerde log(N/df) tabanlı weight olabilir

### Açık takip
- df=30 threshold ile corpus 10K+ olduğunda re-evaluation
- niche_006/007/009 hâlâ fail — answer extraction / chunk size epic adayı (NER kapsamı dışı)

## Faz 6.2 — Cards path NER (#714 / PR #715 — delivered)

### Sorun

#696 audit sonrası yanlış varsayım üzerine kurulan locked decision
[[cards-path-ner-out-of-scope]] (REVOKED 2026-05-11). Gerçek codbase kanıtı:
cards retrieval (\`hybrid_search_agenda_cards\`) production /api/generate ve
/api/generate/stream akışlarının **PRIMARY** retrieval'ı (chunks fallback).
Niş entity sorgu (Karşıyaka maç, Fatih Tutak) doğrudan cards'a gelir.
Cards NER yokluğu = kullanıcı zayıf cevap.

### Implementation (#714)

Chunks Faz 6.1 pattern cards'a port edildi (`hybrid_search_agenda_cards` içine):

1. `_extract_entity_candidates` (mevcut helper)
2. `_ner_idf_match_aids` → article_id seti (chunks ile aynı helper)
3. **Mapping farklı (cards-specific):** article_id → `event_articles.event_id` → `agenda_cards.event_id` → card_id
   ```sql
   SELECT DISTINCT ac.id::text AS card_id
   FROM agenda_cards ac
   JOIN event_articles ea ON ea.event_id = ac.event_id
   WHERE ea.article_id IN (target_aids_from_ner)
   ```
4. RRF stream'e card_id boost (mode-aware K, chunks ile aynı: 20 multi_and, 30 single_rare)

### Etkilenen production endpoint

| Endpoint | Cards path rolü | NER aktif mi? |
|---|---|---|
| `/api/generate` | PRIMARY | ✅ #714 sonrası |
| `/api/generate/stream` | PRIMARY | ✅ #714 sonrası |
| `/api/public/search` | Tek başına | ✅ #714 sonrası |

### Açık takip
- Cards corpus için ayrı NER eval gerek (niche_cards_benchmark adayı)
- Cards NER + chunks NER birlikte rerank LLM yükünü artırır mı? (telemetri)
- agenda_cards.event_id NULL durumlarında NER mapping skip et

## Faz 7a — Numerical entity extraction (#678 / PR #679 — delivered)

Faz 6 sonrası niş sayısal sorgular hala başarısızdı (ABD Hürmüz yüzde 1).
NER prompt `number` type için 🚨 öncelik vurgusu eklendi:
- Yüzde/oran (yüzde 1, %50, 1/3)
- Adet/miktar (21 ülke, 3 ana kent, 30. hafta, 84-82 skor)
- Mesafe/boyut, hız/kapasite
- Tarihsel yıllar (MÖ 408)

Entity cap 30→40. Test article re-NER sonrası:
- ABD Hürmüz d2a47f33: 'yüzde 1', 'iki hafta', '20 yıl' number entity ✅
- Karşıyaka ddae4672: '84-82', '16-14', '30. hafta', '31-48', '62-66' ✅
- Rodos 8b146f02: 26 entity (önceden 11) — niş sayısallar dahil

## Faz 7d — Pipeline savunma katmanları sertleştirme (#725 + #726 + #727 — delivered, 2026-05-12)

Kullanıcı senaryosu: aynı konu/aynı tarih/aynı kullanıcı → sorgu kelimesine göre prod sonuç farklı ("afyon belediye başkanı olayı nedir" insufficient_data, "ne yaptı" completed). 3 katmanlı sertleştirme:

1. **Planner default timeframe (#727)** — Kullanıcı zaman ifadesi vermediyse `son 7 gün` (dar 'bugün' yasak). Planner kelimeye duyarlı non-deterministic davranışını kestirir.
2. **Sufficiency soft-gate (#726)** — `mode='current'` + agenda yetersiz iken erken çıkış KALDIRILDI; chunks-first 90 gün fallback'a güvenilir. Sadece "agenda + chunks her ikisi boş" gerçek son çare. Locked decision detay: [[sufficiency-soft-gate]].
3. **Inspector prod parity (#725)** — `/admin/rag` inceleyici artık planner.timeframes'i SQL filter'a geçirir + `check_sufficiency()` telemetri olarak çalışır (would_have_exited badge). Önceki "tam senkron" iddiası (#718) yarımdı.

3 katman birlikte: planner kelime duyarlılığını yumuşatır → soft-gate emniyet ağı kurar → inspector tanı şeffaf.

**Mini-fix #732 (2026-05-12 followup):** Soft-fail durumunda `gen.warnings.append(...)` SQLAlchemy JSONB column'da ORM "modified" sinyalini tetiklemiyor — reassignment ile düzeltildi (`gen.warnings = list(...) + [...]`). Stream version'da final completion bloğuna `_softfail_warning` eklendi. Kullanıcı UI'da soft-fail warning'i artık görür + DB row'unda persist olur.

**Boru hattı LLM çağrı sayısı (netleştirme):** Triloji **0 yeni LLM çağrısı** ekledi. Mevcut akış aynı kalır — planner → HyDE (cond) → rerank (opsiyonel) → content_generator (max 4 call). Tek farklar: planner prompt ~50 token uzadı (#727, ~3.4 mikro-cent/sorgu); sufficiency erken çıkışı kaldırıldı (#726), önceden `insufficient_data` dönen sorgular artık content_generator çağırıyor (+%0-15 call). Pipeline bir adım daha kısa oldu.

## Faz 7c+ — NER prompt admin tunable (#720 — delivered, 2026-05-12)

DeepSeek NER system prompt'u inline `workers/tasks/entities.py` içinden çekilip
`apps/api/app/prompts/ner.py` modülüne taşındı. **Admin /prompts** sayfasında
"Haber işleme" sekmesi altında `ner_extraction` adıyla runtime override edilebilir
(prompts_store + 5s cache TTL + version history + rollback).

Yan kazanım: tüm DeepSeek call'larının prompt'ları artık admin panelden editable.
PROMPT_REGISTRY 3 → 11 girdi (NER + RAPTOR weekly + country backfill + style
analyzer + HyDE + content_generator 4 variant). Pipeline sekmeleri: ingestion (5)
+ generate (6).

## Açık iyileştirmeler (sonraki — Faz 7b plan)

1. **Embedding upgrade** — bge-m3 → intfloat/multilingual-e5-large
   - Aynı 1024-dim, migration minimal
   - Türkçe için kalibre
   - 109K chunks × yeniden embed (~3 saat background)
   - A/B test ile karar (1 hafta epic)
2. **Entity tip-bazlı RRF weight** — kişi entity match daha güçlü, place orta, number güçlü

## İlişkiler

- [[ragflow-tier-rebuild]] — Faz 1-5 mimari (önceki epic)
- [[smart-quote-normalization]] — quote variants strip (#647)
- [[entity-match-relevance]] — prompt-level alaka kontrolü
- [[cards-path-ner-out-of-scope]]
- [[eval-benchmark-divergence]]
- [[idf-entity-weighting]]
- [[data-model-md]]
- [[prompt-contracts-md]]

## Kaynaklar

- [Issue #667](https://github.com/selmanays/nodrat/issues/667)
- [PR #668](https://github.com/selmanays/nodrat/pull/668)
- `apps/api/app/workers/tasks/entities.py` — DeepSeek extraction worker
- `apps/api/app/core/retrieval.py` — NER stream RRF entegrasyonu
- `apps/api/alembic/versions/20260511_0200_entities_table.py` — migration
