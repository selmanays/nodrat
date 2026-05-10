---
type: decision
title: "Entity match relevance — content_generator alaka kuralı"
slug: "entity-match-relevance"
category: "rag-prompt"
status: "live"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/prompts/content_generator.py§106-156"
  - "GitHub Issue #623 / PR #630 (sıkı versiyon)"
  - "GitHub Issue #623 PR-E.2 / PR #633 (rebalanced)"
  - "GitHub PR #645 (PR-M — backend stem-match terkı)"
  - "GitHub PR #648 (#647 — vakaya özel prompt örnekleri kaldırıldı, retrieval kök sebep çözüldü)"
tags: ["rag", "prompt", "anti-hallucination", "mvp-1-8"]
aliases: ["alaka-check", "irrelevant-sources"]
---

# Entity match relevance

> **TL;DR:** content_generator prompt'ta "ALAKA KONTROLÜ" kuralı. Kategorik benzerlik (sergi/sergi) yetmez ama kelime kelime tam eşleşme de aşırı sıkı. **ANA KONU + KEY ENTITY'lerin EN AZ BİRİ** kart'larda geçmeli. Eşleşmiyorsa LLM `posts=[]`, `warnings=["irrelevant_sources"]` döndürür → kullanıcı "yetersiz veri" görür.

## Bağlam — iki ucta hatalı denemeler

**v1 (PR #630, PR-D)** — KELİMESİ KELİMESİNE eşleşme zorunluydu:
- ✅ Toprakaltı sergisi → Slovenya tüneli REJECTED (entity yok)
- ❌ "21 ülke F-16 radarları kim kazandı" → Northrop Grumman article
  REJECTED (entity tam eşleşmedi, "21 ülke" vs "21 ülkenin")
- Kullanıcı feedback: F-16 yetersiz veri (önceden çalışıyordu)

**v2 (PR #633, PR-E.2)** — yumuşatıldı:
- ANA KONU + KEY ENTITY'lerin EN AZ BİRİ eşleşmeli
- Synonym/abbreviation OK (TB3 ≈ TB-3)
- Parçalı eşleşme OK ("21 ülke F-16 radar" → "F-16 radar" yeter)

## Backend stem-match deneyleri ve terk (PR-J/K/L/M arc, 2026-05-10)

PR-G empty-posts guard, Toprakaltı vakasını yakalamayınca backend'de **kod-düzeyinde** entity-match yardımcısı eklemek denenmişti — Türkçe morfolojisi yüzünden iki kez patladı:

**PR-J (#642)** — exact-match: query anahtar kelimesi source'ta birebir geçmeli.
- Çıktı: F-16 query "sözleşmeyi" vs source "sözleşme" → false negative.
- PR-K ile kaldırıldı.

**PR-L (#644)** — stem-match: en uzun kelime (named entity proxy) ilk 4 harfi source'ta geçmeli.
- F-16 false negative düzelmiş gibi görünüyordu (planner reformulation senaryosunda yine fail edebilir, edge case).
- Toprakaltı false positive: `"toprakaltı"` (10 char) ve `"sergisiyle"` (10 char) tied → Python `max(meaningful, key=len)` ilk elementi alıyor → `"sergisiyle"` stem `"serg"` Slovenya source'ta → PASS, halüsinasyon çıkış yolu açıldı.
- **PR-M (#645)** ile kaldırıldı.

**Çıkarılan ders:**
Türkçe ek-kök ayrımı + tie-break belirsizliği backend'de güvenilir entity match'i mümkün kılmıyor (en azından regex/stem seviyesinde). LLM zaten prompt #13 örnekleriyle **anlam-bazlı** alaka kontrolü yapıyor (Toprakaltı vs Slovenya konkret örneği §127-134). Code-level "yedek koruma" eklemek yerine **prompt'u sağlamlaştır + LLM'in irrelevant_sources flag'ine güven** stratejisi seçildi.

## Yamaların kaldırılması ve kök sebep çözümü (#647 / PR #648, 2026-05-10)

PR-M sonrası kullanıcı kritik soru sordu: "Sistemde tam olarak neleri değiştirdin? Yama yaptın mı?"

İtirafla yamalar tespit edildi:
1. Prompt §127-134: "Toprakaltı sergisi vs Slovenya tüneli ALAKASIZ" konkret örneği — tek vakaya özel
2. Prompt §219-222: "Northrop Grumman F-16" konkret örneği (Örnek 3) — tek vakaya özel
3. Prompt §251-260: F-16 vakası örneği (Kural #16) — tek vakaya özel

Bu örnekler vakayı prompt'a ezberletmek (transfer yok). Asıl sorun retrieval seviyesinde olduğu görüldü:

**KÖK SEBEP (DB analizi sonucu):**
Bianet Toprakaltı article DB'de var (`title="Azıcık radyasyon kemiklere yararlıdır"`, subtitle'da "Toprakaltı"), chunk'a giriyor, embedding mevcut. Ama `retrieval.py` SQL `REPLACE` chain'i sadece ASCII apostrof ve `chr(8217)` siliyordu, `chr(8221)` (RIGHT DOUBLE QUOTATION) silinmiyordu. Bianet `"Toprakaltı"` ifadesinde curly çift tırnak var → normalize sonrası phrase ILIKE `%toprakaltı sergisi%` patladı.

**Çözüm — sistemik:** Bkz [[smart-quote-normalization]] decision. 19 quote varyantı tek noktadan strip + article metadata sparse pool + entity-aware rerank boost. Tüm değişiklikler GENEL — vakaya özel kod yok.

Yamalar yerine prompt #13 GENEL kural metniyle sadeleştirildi (kategori benzerliği yetmez, anlam-bazlı entity match gerek). LLM artık herhangi bir vaka için aynı kuralı uyguluyor.

Üretim doğrulaması (PR #648 deploy sonrası):
- "Toprakaltı sergisi ne zamandı" → Bianet article #1'de retrieve ediliyor ✅ (eskiden boş)
- "F-16 21 ülke kim kazandı" → Northrop Grumman C4Defence #1 ✅
- "MKE SAHA 2026", "Türkiye ekonomisi", "Bayraktar TB3" → regression yok ✅

## Kural

```
EŞLEŞME KRİTERİ:
✅ ANA KONU + 1+ KEY ENTITY kart'larda geçiyorsa → ALAKALI
✅ Synonym/abbreviation OK
✅ Parçalı eşleşme OK
❌ Sadece KATEGORİ ortak (sergi/sergi) → ALAKASIZ
❌ Hiçbir entity geçmiyor, sadece tema benzer → ALAKASIZ
```

## Yasaklar

```
❌ Kategori ortaksa "alakalı" demek (sergi/sergi)
❌ UYDURMA başlık + ilgisiz kart toplama
   (Toprakaltı sergi sorusu + Slovenya tüneli + uydurma "Toprakaltı
    Sergileri ve Kültürel Etkinlikler" başlığı KESİN HAYIR)
❌ "Yarım bilgi de olsa cevap üreteyim"
```

## Etki — üretim vakaları

| Sorgu | Kart | Eşleşme | Sonuç |
|---|---|---|---|
| F-16 21 ülke kim kazandı | Northrop Grumman 21 ülke F-16 radar | F-16+21+radar match | ✅ ALAKALI |
| Toprakaltı sergisi | Slovenya tünel sergi | sadece "sergi" kategori | ❌ ALAKASIZ |
| Toprakaltı sergisi | İstanbul Toprakaltı Sergisi | "Toprakaltı" entity | ✅ ALAKALI |
| iPhone 17 | Samsung Galaxy yapay zeka | hiç entity yok | ❌ ALAKASIZ |

## İlişkiler

- [[multi-query-rewrite]] — retrieval geniş arama yapar, prompt sonra elemeler
- [[multi-source-synthesis]] — alakalı kartlar üzerinde sentez
- [[hyde-feature-flag]] — opsiyonel ek varyant

## Kaynaklar

- `apps/api/app/prompts/content_generator.py` §106-156 (alaka kontrolü prompt #13)
- [PR #630](https://github.com/selmanays/nodrat/pull/630) — sıkı versiyon (v1, kelimesi kelimesine)
- [PR #633](https://github.com/selmanays/nodrat/pull/633) — rebalance (v2, KONU+ENTITY)
- [PR #642](https://github.com/selmanays/nodrat/pull/642) → [#643](https://github.com/selmanays/nodrat/pull/643) — PR-J backend exact-match denemesi + PR-K geri alma
- [PR #644](https://github.com/selmanays/nodrat/pull/644) → [#645](https://github.com/selmanays/nodrat/pull/645) — PR-L backend stem-match denemesi + PR-M geri alma; sorumluluk LLM prompt'unda
