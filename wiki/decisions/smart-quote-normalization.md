---
type: decision
title: "Smart-quote normalization — RAG körlük kök sebebi"
slug: "smart-quote-normalization"
category: "rag"
status: "live"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/core/retrieval.py§70-170 (strip_quote_variants + _build_sql_quote_strip)"
  - "apps/api/app/core/retrieval.py§830-900 (chunks SQL — article metadata sparse pool)"
  - "apps/api/app/core/rerank.py§24-110 (entity-aware boost)"
  - "GitHub Issue #647 / PR #648 (kök çözüm) + PR #650 (streaming parity)"
tags: ["rag", "retrieval", "normalization", "lexical-match", "mvp-1-8"]
aliases: ["quote-strip", "lexical-recall-fix"]
---

# Smart-quote normalization

> **TL;DR:** Bianet/Hürriyet/T24 gibi smart-quote (`"`/`"`/`'`/`'`) kullanan kaynaklarda RAG retrieval phrase-match patlıyordu — sadece `chr(39)` ve `chr(8217)` siliniyordu, `chr(8221)` (RIGHT DOUBLE QUOTATION) silinmiyordu. Yüzlerce article görünmez kalıyordu. Çözüm: 19 quote varyantını Python + SQL'de tek noktadan strip eden `strip_quote_variants` helper + article-level metadata sparse pool'a + entity-aware rerank boost.

## Bağlam — körlük teşhisi

Üretim sorgusu: `Toprakaltı sergisi ne zamandı` → "Yeterli kaynak yok"

Ama Bianet article DB'de var:
```
title:    "Azıcık radyasyon kemiklere yararlıdır"
subtitle: ... Onur Gökmen'in "Toprakaltı" sergisi 3 Mayıs'a dek ...
chunk:    ... onur gökmenin "toprakaltı" sergisi 3 mayısa ...
```

SQL test: `t_norm ILIKE '%toprakaltı sergisi%'` → **FALSE**

Eski normalize chain:
```sql
LOWER(REPLACE(REPLACE(c.chunk_text, chr(39), ''), chr(8217), ''))
```

Sadece **ASCII apostrof** ve **U+2019 RIGHT SINGLE** silinir. Bianet `"Toprakaltı"` ifadesinde **U+201D RIGHT DOUBLE QUOTATION** var — silinmiyor → `toprakaltı"` ile `sergisi` arasında `"` karakteri kaldı → phrase ILIKE patlıyor.

> ⚠️ Bu bug'ın etki alanı tek vaka değil — Bianet, Hürriyet, T24, Diken, Evrensel başta olmak üzere smart-quote kullanan **tüm** Türk haber kaynakları yüzlerce article'da retrieval'da görünmez kalmıştı.

## Çözüm — 3 sistemik fix (PR #648)

### Fix #1 — quote normalization (kök sebep)

Tüm major quote varyantları (19 char) tek noktadan strip edilir:
- Single: `'` `'` `'` `‚` `‛` `′` `ʼ` `ʹ`
- Double: `"` `"` `"` `„` `‟` `″`
- Guillemets: `«` `»` `‹` `›`
- Backtick: `` ` ``

`strip_quote_variants(text)` Python helper + `_build_sql_quote_strip(column_expr)` SQL chain builder → Python normalize ile SQL deterministik eşleşme.

```python
def strip_quote_variants(text):
    s = text
    for q in _QUOTE_CHARS_TO_STRIP:
        if q in s: s = s.replace(q, "")
    return s
```

### Fix #2 — article metadata sparse pool

`hybrid_search_chunks` SQL'i artık `chunk_text` + `article.title || ' ' || article.subtitle` üzerinden `ILIKE`/trigram match yapar. Subtitle-only entity'ler (Bianet pattern: title generic, subtitle özel ad) chunk'a düşmemiş olsa bile retrieve edilir.

```sql
WITH norm AS (
  SELECT c.id, c.article_id,
         LOWER(strip_quotes(c.chunk_text)) AS t_norm,
         LOWER(strip_quotes(a.title || ' ' || COALESCE(a.subtitle,'')))
            AS m_norm
  FROM article_chunks c JOIN articles a ON ...
)
WHERE n.t_norm ILIKE :phrase OR n.m_norm ILIKE :phrase OR ...
```

### Fix #3 — entity-aware rerank boost (genel kural)

`_extract_entity_candidates(query)`: query'den >=5 char özel-ad-benzeri token çıkar, TR/EN stop kelimeleri ele. `_entity_match_bonus(query_entities, row)`: passage'de geçen entity başına +0.025 (cap 0.10). Reject DEĞİL — sıralama yardımı.

Cross-encoder düşük logit verirse bile lexical match high-recall'u korur. Vakaya özel kod yok — Toprakaltı, Bayraktar, F-16, MKE, Northrop, Galatasaray, COVID-19... herhangi bir entity için aynı çalışır.

## Üretim doğrulama (E2E test, PR #648 sonrası)

| Sorgu | Top sonuç | Durum |
|---|---|---|
| "Toprakaltı sergisi ne zamandı" | **Bianet #1** ✅ | Eskiden boş, şimdi #1 |
| "F-16 21 ülke kim kazandı" | C4Defence Northrop #1 ✅ | Regression yok |
| "MKE SAHA 2026" | SavunmaSanayiST #1 ✅ | Regression yok |
| "Türkiye ekonomisi" | Şimşek ekonomi #1 ✅ | Regression yok |
| "Bayraktar TB3 İHA" | Selçuk Bayraktar SAHA 2026 ✅ | Regression yok |
| `"Toprakaltı" sergisi` (quote'lı) | Bianet #2 ✅ | Quote-aware sorgu |

## Streaming endpoint parity (PR #650 follow-up)

PR #648 sonrası kullanıcı UI'da yine "yetersiz kaynak" alıyordu. Sebep: `/app/generate-stream` endpoint'i (UI'nin kullandığı) MVP-1.8 PR-A/B/H mimarisinden hiçbirini almamıştı:
- `agenda_cards` primary, `chunks` sadece `if not agenda_cards` → genelde tetiklenmiyordu
- `top_k=4`, `since_hours=168` (7 gün) — kısıtlı
- Multi-query rewrite + RRF YOK
- Source diversity cap YOK

PR #650 streaming endpoint'i `app_generate.py` ile birebir parity'e getirdi:
- Multi-query rewrite + RRF k=60 (PR-B parity)
- Source diversity max 2/domain (PR-A parity)
- Chunks ALWAYS-ON 90 gün corpus, top_k 15+ (PR-H parity)
- content_top_k range 3-15 (Perplexity-style)

Şu an UI Toprakaltı sorgusu agenda + chunks her ikisinden de retrieve ediyor; Bianet article supplementary_chunks #1 olarak LLM context'inde.

## Yamaların kaldırılması

PR #648 ile birlikte content_generator prompt'tan 3 vakaya özel örnek kaldırıldı, genel kural metni geldi:
- §127-134: Toprakaltı/Slovenya konkret örneği → genel "kategori örtüşmesi yetmez, entity match gerek" kuralı
- §219-222: Northrop Grumman F-16 örneği → genel format şablonu
- §251-260: F-16 vakası örneği (Kural #16) → genel tek-kaynak format şablonu

Sorumluluk artık prompt'a vaka ezberletmek değil — RAG retrieval seviyesinde recall doğru.

## Trade-off

**Pro:**
- Yüzlerce/binlerce smart-quote kullanan article retrievable
- Sistemik çözüm (vakaya özel kod yok)
- Subtitle-only entity'ler (Bianet pattern) lexical recall kazanılır
- Entity-aware boost cross-encoder negatif logit edge case'inde recall korur
- Unit test 21 yeni test (11 normalize + 10 entity boost)

**Con:**
- Sparse SQL biraz büyüdü (REPLACE chain × 19 quote variant + meta concat)
- Latency +5-10ms (dramatic değil, milisaniye seviyesi)

## İlişkiler

- [[chunks-first-retrieval]] — chunks always-on retrieval (PR-H)
- [[multi-query-rewrite]] — chunks search üzerinde uygulanır
- [[entity-match-relevance]] — prompt #13 alaka kontrolü
- [[source-diversity-cap]] — chunks sonrası max 2/domain
- [[multi-source-synthesis]] — sentez generation'da

## Açık sorular / TODO

- [ ] Diakritik normalize (Türkçe İ→i, ç→c) ek varyant — şu an Postgres `LOWER` Latin1 davranışı
- [ ] Entity bonus min_len=5 sertliği: "F-16" 4 char (tire dahil) bonus alamıyor — tire-aware min_len 4 yapılabilir (ileri iterasyon)
- [ ] Embedding upgrade değerlendirmesi (bge-m3 → daha Türkçe-aware) — ayrı issue

## Kaynaklar

- `apps/api/app/core/retrieval.py` §70-170 (`strip_quote_variants`, `_build_sql_quote_strip`)
- `apps/api/app/core/retrieval.py` §830-900 (chunks SQL — meta concat sparse)
- `apps/api/app/core/rerank.py` §24-110 (entity bonus + extractor)
- `apps/api/tests/unit/test_query_normalize.py` (11 quote variant test)
- `apps/api/tests/unit/test_rerank.py` (10 entity bonus test)
- [Issue #647](https://github.com/selmanays/nodrat/issues/647)
- [PR #648](https://github.com/selmanays/nodrat/pull/648)
