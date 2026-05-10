---
type: concept
title: "Multi-source synthesis — Perplexity-style sentez"
slug: "multi-source-synthesis"
category: "rag-prompt"
status: "live"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/prompts/content_generator.py§155-186"
  - "GitHub Issue #618 PR-E.3 / PR #633"
  - "GitHub Issue PR-F / PR #634"
tags: ["rag", "prompt", "perplexity", "synthesis", "mvp-1-8"]
aliases: ["multi-source", "sentez"]
---

# Multi-source synthesis

> **TL;DR:** content_generator prompt'ta **her önemli iddia için min 2 kaynak referansı** zorunluluğu. Yan-yana liste yerine sentez. Tek-kaynak iddia varsa disclaimer ile. Perplexity'nin asıl farkı: kaynaklar arası **agreement scoring** + **per-source perspective** ([[cross-source-agreement]]).

## Bağlam

Kullanıcı feedback'i: "her paragraf 1 kaynak — Perplexity'den çok gerideyiz". Önceki content_generator çıktıları:

❌ **YANLIŞ format** (yan-yana liste):
> "Türkiye savunma ihracatı arttı [1]. SAHA fuarı düzenlendi [2]."
> (Sentez yok, perspektif yok, kaynaklar arası ilişki belirsiz)

✅ **DOĞRU format** (multi-source synthesis, PR-E.3 + PR-F):
> "Türkiye savunma ihracatı 2026'da %42 artarak 11 milyar dolara ulaştı —
> SSB Başkanı Görgün resmi açıklamasında doğruladı [1], MKE'nin yeni silah
> sistemleri tanıtımı bu büyümenin sektörel sebeplerini gösteriyor [2],
> Bayraktar İHA satışları ise ana itici güç olarak öne çıkıyor [3][4]."

## Kural setti

### A) Çoklu kaynak referansı

```
✅ DOĞRU: "Türkiye savunma ihracatı 2026'da %42 arttı [1][3]. Bu artışın
          ana sebepleri Bayraktar İHA'lar ve ASELSAN sözleşmeleri [2][4]."
❌ YANLIŞ: "Türkiye savunma ihracatı arttı [1]." (tek kaynak iddia)
```

### B) Agreement scoring ([[cross-source-agreement]])

- **HEMFİKİR** (3+ kaynak): "Birden fazla kaynak X'i teyit ediyor [1][3][4]"
- **KISMEN ÇELİŞEN**: "Resmi X derken bağımsız analiz Y görüş bildiriyor"
- **TAM ÇELİŞEN**: "Kaynaklar Z konusunda farklı: [1] X, [2] tam tersi"
- **TEK KAYNAK**: "Bu bilgi tek kaynaktan — diğer kaynaklarda teyit yok"

### C) Per-source perspective

- Resmi (Anadolu Ajansı, TRT) → bürokratik açı
- Bağımsız (Bianet, Diken, Evrensel) → eleştirel/sivil
- Sektör (C4Defence, Webtekno, Bloomberg) → teknik/sektörel
- Mainstream (Hürriyet, Habertürk) → genel okur

## Yasaklar

```
❌ "Kaynak A: X. Kaynak B: Y." (yan-yana liste, sentez yok)
❌ Perspektif/açı belirtmemek (kaynak çeşitliliği farkı yok)
❌ Tek-kaynak iddia + disclaimer eksik
```

## Etki

- Kullanıcı çıktıları Perplexity-style multi-source görür
- Halüsinasyon riski azalır (cross-source agreement zorunlu)
- Çelişen kaynaklar açık belirtim → kullanıcı bilgi durumunu doğru değerlendirir

## İlişkiler

- [[cross-source-agreement]] — agreement scoring detayı
- [[entity-match-relevance]] — alaka kontrolü (sentez öncesi)
- [[source-diversity-cap]] — diversity sentez kalitesi için
- [[twenty-five-word-quote-cap]] — FSEK uyumu (sentez içinde quote)

## Kaynaklar

- `apps/api/app/prompts/content_generator.py` §155-186
- [PR #633](https://github.com/selmanays/nodrat/pull/633) — PR-E.3 multi-source ilk kural
- [PR #634](https://github.com/selmanays/nodrat/pull/634) — PR-F per-source perspective derinleştirme
