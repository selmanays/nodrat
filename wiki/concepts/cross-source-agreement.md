---
type: concept
title: "Cross-source agreement — kaynaklar arası onay scoring"
slug: "cross-source-agreement"
category: "rag-prompt"
status: "live"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/prompts/content_generator.py§158-186"
  - "GitHub Issue PR-F / PR #634"
tags: ["rag", "prompt", "perplexity", "consensus", "mvp-1-8"]
aliases: ["agreement-scoring", "consensus-scoring"]
---

# Cross-source agreement

> **TL;DR:** Generation prompt'unda kaynaklar arası **agreement scoring**: aynı iddiayı 2+ kaynak teyit ediyorsa "yüksek güven", tek kaynak ise disclaimer. Çelişen kaynaklar açık belirtim. [[multi-source-synthesis]]'in alt katmanı.

## 4 agreement level

### 1. HEMFİKİR (3+ kaynak teyit)
```
"Birden fazla kaynak X'i teyit ediyor [1][3][4]"
```
En yüksek güven seviyesi. Generation summary'de bu pattern dominant olmalı.

### 2. KISMEN ÇELİŞEN (perspektif farkı)
```
"Resmi açıklamaya göre X (Anadolu Ajansı), bağımsız analiz Y görüş
bildiriyor (Bianet)"
```
Per-source perspective ([[multi-source-synthesis]] §C) ile birleşir. Resmi vs bağımsız vs sektör ayrımı.

### 3. TAM ÇELİŞEN (data conflict)
```
"Kaynaklar Z konusunda farklı: [1] X derken [2] tam tersini söylüyor"
```
Halüsinasyon DEĞİL, doğru bilgi sunumu. Kullanıcı bilgi durumunu doğru değerlendirir.

### 4. TEK KAYNAK (disclaimer)
```
"Bu bilgi tek kaynaktan (Hürriyet) — diğer kaynaklarda teyit yok"
```
"Tek kaynaklı iddia" şeffaflığı. Kullanıcı kaynağa güven verecek.

## Üretim örneği

**Sorgu:** "Türkiye savunma ihracatı son durum"

**RAG cards:**
- [1] Anadolu Ajansı — "SSB Başkanı: 11 milyar dolar hedef"
- [2] C4Defence — "MKE SAHA 2026'da yeni silahlar tanıttı"
- [3] Webtekno — "Bayraktar TB3 satışı arttı"
- [4] Hürriyet — "Türkiye ihracatta dünya 10'a giriyor"

**DOĞRU summary (PR-F):**
> "Türkiye savunma ihracatı 2026'da rekor seviyeye ulaştı — kaynaklar
> hemfikir [1][3][4]. SSB resmi açıklamasında 11 milyar dolar hedefi
> doğrulandı [1], sektörel olarak Bayraktar TB3 ve MKE'nin yeni
> silah sistemleri ana itici güçler [2][3]. Mainstream basın
> Türkiye'nin küresel sıralamada ilk 10'a girme hedefini öne çıkarıyor [4]."

**YANLIŞ summary (PR-F öncesi):**
> "SSB 11 milyar hedef [1]. MKE silah tanıttı [2]. TB3 satışı arttı [3].
> Türkiye ilk 10'a giriyor [4]." (yan-yana, sentez yok, agreement yok)

## Önyargı koruması

Eğer kart'ların tümü aynı politik tarafta ise (örn. hep mainstream pro-government):
```
"Sağlanan kaynaklar büyük ölçüde resmi/mainstream perspektiften —
bağımsız medyada teyit yok"
```
Kullanıcı bunu okur, **kendi kararını verir**. Sistem önyargılı sentez **yapmaz**.

## İlişkiler

- [[multi-source-synthesis]] — üst kavram
- [[entity-match-relevance]] — alaka kontrolü (önce)
- [[source-diversity-cap]] — agreement için domain çeşitliliği gerekli

## Kaynaklar

- `apps/api/app/prompts/content_generator.py` §158-186
- [PR #634](https://github.com/selmanays/nodrat/pull/634)
