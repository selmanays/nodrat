---
description: Wiki mevcut durum — sayfa sayısı, son ingest, açık çelişkiler, sıradaki öneri
---

# /wiki-status

5 başlıkta wiki snapshot raporu:

## 1. İstatistik

`wiki/index.md` son section'ından oku ("İstatistik"):
- Toplam sayfa
- Kaynak sayısı / 32
- Son ingest tarihi + dokümanı
- Son lint tarihi
- Açık çelişki sayısı
- Wiki'deki locked decisions / INDEX §4 toplam

## 2. Son aktivite

`wiki/log.md` son 5 girişini listele:
```bash
grep -E "^## \[" wiki/log.md | tail -5
```

## 3. Açık çelişkiler

```bash
grep -rln "⚠️ Çelişki" wiki/ | wc -l   # toplam
grep -rl "⚠️ Çelişki" wiki/ | head -5  # ilk 5 dosya
```

İlk 3'ünün özet satırlarını oku ve kullanıcıya göster.

## 4. Locked decisions kapsama

```bash
WIKI_DEC=$(ls wiki/decisions/*.md 2>/dev/null | wc -l)
INDEX_DEC=$(grep -c "^✅" INDEX.md)
echo "Wiki: $WIKI_DEC / INDEX §4: $INDEX_DEC"
```

INDEX §4'te locked olan ama wiki'de henüz sayfası olmayan kararları öne çıkar.

## 5. Sıradaki ingest önerisi

`wiki/log.md` son giriş notlarındaki "Sıradaki ingest önerileri" bölümünden al. Yoksa kanonik sıra:

```
1. docs/product/prd.md (kanonik kök)
2. docs/strategy/discovery-validation.md + docs/validation/research-findings.md (persona)
3. docs/engineering/prompt-contracts.md (R-PRD-01 halü detayı)
4. docs/engineering/data-model.md (12 tablo entity'leri)
5. docs/engineering/api-contracts.md (~50 endpoint)
6. docs/strategy/competitive-analysis.md (R-MKT-01 detay)
7. docs/strategy/pricing-strategy.md + unit-economics.md (tier mapping)
8. docs/legal/* (KVKK, FSEK, takedown, ROPA)
9. docs/design/* (UX, design tokens)
10. docs/product/information-architecture.md
```

## Format

10-15 satır özet rapor — emoji yok, kısa, eyleme yönelik:

```
Wiki: N sayfa · 2/32 kaynak · son ingest: ... · son lint: ...
Aktivite (son 5):
  · ...
Açık çelişki: M (en kritik 3: ...)
Locked: P/Q (eksik: ...)
Sıradaki: <yol> (~tahmini ekleme)
```

## Hiçbir şey yazma

Bu komut **read-only**. Sadece raporlar; wiki'ye dokunmaz.
