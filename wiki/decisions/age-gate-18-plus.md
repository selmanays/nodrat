---
type: decision
title: "Yaş gate 18+ (16+ değil)"
slug: "age-gate-18-plus"
category: "legal-policy"
status: "locked"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docs/legal/tos.md §4 Hesap Oluşturma"
  - "docs/legal/kvkk-aydinlatma.md §3 Veri Sahibi Hakları"
  - "INDEX.md §4 locked decisions"
tags: ["legal", "compliance", "decision", "age-gate", "mvp-1"]
---

# Yaş Gate 18+

> **TL;DR:** Nodrat hizmeti **yalnızca 18 yaş üstü** kullanıcılara açık. 16+ değil. Sebep: ToS, telif (FSEK), reklam içeriği, KVKK rıza ehliyeti, "siyasi içerik" hassasiyeti.

## Karar

```text
✅ Kabul: yaş ≥ 18 (kayıt sırasında doğrulama)
❌ Red: yaş < 18 (kayıt reddi, KVKK velinin onayı yetersiz)
```

## Gerekçeler

1. **KVKK md.5/2-a açık rıza ehliyeti** — Türkiye'de 18+ tam ehliyet; 18 altı veli onayı gerek + ek karmaşıklık
2. **Telif (FSEK)** — kullanıcı oluşturduğu içerikten sorumlu; reşit sorumluluğu gerek
3. **Siyasi içerik hassasiyeti** — kullanıcı persona'sı P1A (politik creator); 18 altı erişim ürün vizyonu dışı
4. **Reklam yasakları** — alkol/tütün referansları (FSEK ve ad regulations) — 18 altı içerik üretimi yasak
5. **Yasal sorumluluk** — bir 18 altı kullanıcının halüsinasyon temelli yanlış üretim yapması = velinin sorumluluğu — karmaşık

## Uygulama

- **Kayıt formu:** doğum tarihi alanı zorunlu; computed `age ≥ 18` gate
- **ToS §4:** "Hizmeti yalnızca 18 yaş ve üzeri kullanıcılar kullanabilir."
- **KVKK Aydınlatma §3:** Veri Sahibi Hakları açıklamasında 18+ koşulu
- **Privacy Policy:** açık ifade
- **Admin override:** YOK (her durumda 18+ zorunlu)

## Re-evaluation Tetikleyicileri

- Pazar verisi 16-18 yaş yoğun talep gösterirse + yasal danışman görüşü değişirse
- Eğitim sektörü tier'ı için (öğretmen aracı) gözden geçirilir (ayrı epic)

## İlişkiler

- [[tos-md]] §4 Hesap Oluşturma
- [[kvkk-aydinlatma-md]] §3 Veri Sahibi Hakları
- [[privacy-policy-md]]

## Kaynaklar

- [docs/legal/tos.md](../../docs/legal/tos.md) §4
- INDEX.md §4 (locked decisions)
