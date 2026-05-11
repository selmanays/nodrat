---
type: entity
title: "R-LGL-02 — FSEK Telif Tazminat"
slug: "risk-fsek-telif"
category: "risk"
status: "live"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/strategy/risk-register.md§3.1"
  - "docs/strategy/risk-register.md§2.1"
  - "docs/legal/compliance-brief.md§3"
tags: ["risk", "legal", "fsek", "copyright", "red"]
aliases: ["R-LGL-02", "fsek-risk", "telif-tazminat"]
---

# R-LGL-02 — FSEK Telif Tazminat

> **TL;DR:** Proje genelindeki en yüksek skorlu tek risk (skor **12 🔴**). Bir gazete (Sabah/Sözcü vb.) Nodrat'ı haberlerini "yeniden yayınladığı" iddiasıyla 5846 sayılı FSEK altında tazminat davası açabilir. Tazminat 50K-1M TL + reputational damage. 7 katmanlı mitigation aktif; en kritik mitigation [[twenty-five-word-quote-cap]].

## Tanım

5846 sayılı Fikir ve Sanat Eserleri Kanunu (FSEK) Türkiye'de telif eserin yeniden yayınlanmasını kısıtlar. §35 iktibas hakkı "amaçla mütenasip" sınırlı alıntı tanır ama Yargıtay içtihadı bu sınırı 25-50 kelime aralığında "kısa iktibas" olarak belirler.

Nodrat haber metinlerini iç RAG'de tutar (full text — internal use OK) ama kullanıcıya gösterilen output'ta tam metin reproduction yapamaz. Risk: prompt edge-case'lerinde LLM'in 25 kelimeden uzun direct quote üretmesi → "yeniden yayın" tanımına girer.

## Skor

| Boyut | Değer | Açıklama |
|---|---|---|
| **Olasılık** | 3 | Türkiye'de henüz haber-RAG davası yok ama olabilir; emsal davalar mümkün. |
| **Etki** | 4 | Tazminat 50K-1M TL + brand damage + KVKK Kurul incelemesi tetikleyici. |
| **Skor** | **12** | 🔴 Kırmızı (≥9 yüksek öncelik). |

Kabul kriteri (mitigation tam uygulandığında): Skor 12 → 6 (Olasılık 3→2, Etki 4→3).

## Mitigation matrisi (risk-register §3.1)

| ID | Önlem | Durum |
|---|---|---|
| **M1** | Hard rule: Output'ta ≤25 kelime direct quote | ✅ locked ([[twenty-five-word-quote-cap]]) |
| M2 | Tüm üretimlerde kaynak link gösterimi | ✅ enforced |
| M3 | ToS'ta "kullanıcı sorumluluğu" net madde | ✅ ToS draft hazır (avukat final review bekliyor) |
| M4 | Source ekleme: paywall HARAM, robots.txt uyum | ✅ INDEX §4 locked |
| M5 | Avukat ön-görüş (Faz 0) | ✅ tamamlandı (opinion-integration.md) |
| M6 | Output kalite kontrol: alıntı tespit + flag | ✅ output_validator (post-process) |
| M7 | Gazete partnership stratejisi (Q3 2026+) | ⏳ planlanıyor |

## Tetikleyici

```text
Tetikleyici: Tam metin reproduction kullanıcıya gösterimi
Senaryo: Kullanıcı "X gazetesindeki son haberi paylaş" der.
         LLM 80 kelimelik direct quote üretir.
         Kullanıcı X'te paylaşır.
         Gazete avukatları "yeniden yayın" iddiasıyla tazminat talep eder.
```

## Kontrol checkpoint'leri

```text
- Faz 1 sonu: Avukat review kılavuzu uygulanıyor mu (post-hoc ✅)
- Faz 3 sonu: 100 örnek output review (telif riski) — yapılmalı
- Aylık: Kaynak başına direct quote oranı raporu — operasyonel runbook
```

## Çapraz referanslar

- **Bağlı kararlar:** [[twenty-five-word-quote-cap]] (M1), [[mvp-1-scope-lock]] (M4 → robots.txt sıfır tolerans implicit).
- **Bağlı kavramlar:** [[risk-scoring]] (skor metodolojisi).
- **İlgili topics:** [[risk-catalog]] (top-7 kırmızı liste).
- **İlgili dokümanlar:** [docs/legal/compliance-brief.md §3](../../docs/legal/compliance-brief.md), [docs/legal/tos.md](../../docs/legal/tos.md), [docs/legal/scraping-policy.md](../../docs/legal/scraping-policy.md).

## Açık sorular / TODO

- **M6 output validator coverage:** 100 örnek output review § 3.1'de "Faz 3 sonu" için planlanmış. MVP-1 production'da; bu review gerçekten yapıldı mı? Citation validator (#180) cosine ≥0.55 threshold mevcut.
- **M7 partnership timeline:** Q3 2026 hedefli. Kim/hangi yayıncıyla başlanacak (Sabah-Demirören, DOĞAN, Habertürk)? GTM dokümanı var mı?
- **Yargıtay içtihadı tarama:** "25 kelime" kararı içtihat hangi davalardan? Compliance brief §3'te emsal davalar listeleniyor mu? (kontrol edilmeli)

## İlişkiler

- [[own-slm-strategy]]
- [[risk-register-md]]

## Kaynaklar

- [docs/strategy/risk-register.md §3.1 (R-LGL-02 detay)](../../docs/strategy/risk-register.md)
- [docs/strategy/risk-register.md §2.1 (top kırmızı tablosu)](../../docs/strategy/risk-register.md)
- [docs/legal/compliance-brief.md §3 (FSEK)](../../docs/legal/compliance-brief.md)
- [docs/legal/scraping-policy.md](../../docs/legal/scraping-policy.md)
- [INDEX.md §4](../../INDEX.md) — locked decisions (25 kelime, robots.txt, paywall)
