---
type: concept
title: "Risk skor metodolojisi (1-25 olasılık × etki)"
slug: "risk-scoring"
category: "framework"
status: "live"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/strategy/risk-register.md§1"
tags: ["risk", "methodology", "scoring", "framework"]
aliases: ["risk-score", "risk-matrix", "olasılık-etki"]
---

# Risk skor metodolojisi

> **TL;DR:** Nodrat risk register'ı standart 1-25 ölçeği kullanıyor: skor = olasılık (1-5) × etki (1-5). 🔴 9+ yüksek öncelik (mitigation gerek), 🟡 4-8 orta (izleme), 🟢 1-3 düşük (kabul edilebilir). 8 risk kategorisi: LGL, PRD, TCH, OPS, FIN, MKT, SEC, PEO.

## Tanım

Standart "risk matrisi" yaklaşımı. Her risk için iki bağımsız skor:

- **Olasılık (Probability):** Riskin gerçekleşme ihtimali.
- **Etki (Impact):** Gerçekleşirse Nodrat'a verdiği zarar.

Çarpım skoru ile riskler önceliklendirilir.

## Olasılık (1-5)

| Skor | Anlamı | Örnek |
|---|---|---|
| 1 | Çok düşük | "Hiç olmayacak gibi" — emsal yok, savunma sağlam |
| 2 | Düşük | Yıllık <%5 olasılık |
| 3 | Orta | "Olabilir" — emsal var, savunma kısmen |
| 4 | Yüksek | Yıllık ≥%30 olasılık — kontrol zayıf veya tetikleyici sık |
| 5 | Çok yüksek | "Kesin olacak" — kontrol yok |

## Etki (1-5)

| Skor | Anlamı | Örnek |
|---|---|---|
| 1 | Önemsiz | Düzeltme <1 saat, müşteri hissetmez |
| 2 | Düşük | Düzeltme <1 gün, küçük müşteri etkisi |
| 3 | Orta | Düzeltme 1-7 gün, brand damage azı, çare var |
| 4 | Yüksek | Tazminat ≥50K TL, retention impact, çare zor |
| 5 | Kritik | Servis kapatma, ≥1M TL kayıp, KVKK Kurul kararı |

## Skor

```text
Skor = Olasılık × Etki  (range: 1-25)

Kırmızı 🔴: 9+   (yüksek öncelik, mitigation gerek)
Sarı   🟡: 4-8  (izleme, plan)
Yeşil  🟢: 1-3  (kabul edilebilir)
```

## 8 risk kategorisi

| Kod | Anlamı |
|---|---|
| **LGL** | Yasal & Compliance (FSEK, KVKK, FSEK, 5651, vergi, basın kanunu) |
| **PRD** | Ürün riski (kalite, kullanıcı deneyimi, halüsinasyon, retention) |
| **TCH** | Teknik altyapı (pgvector limit, queue backlog, Playwright kullanım) |
| **OPS** | Operasyonel (HTML kırılganlık, VPS arıza, backup, spam) |
| **FIN** | Finansal / cost (LLM cost runaway, provider instability, ödeme) |
| **MKT** | Pazar / rekabet (ChatGPT, WTP, ekonomik downturn) |
| **SEC** | Güvenlik (admin breach, prompt injection, API key sızıntısı) |
| **PEO** | İnsan / takım (solo founder bandwidth, burnout) |

## Risk register dağılımı (2026-05-07)

```text
🔴 Kırmızı (skor ≥9):  7 risk
🟡 Sarı (4-8):         17 risk
🟢 Yeşil (1-3):         6 risk (1 ÇÖZÜLDÜ — R-OPS-05 görsel storage)
─────────────────────────────────
Toplam:               30 risk
```

Detay: [[risk-catalog]].

## Mitigation kabul kriteri

Bir risk skorunun düşürülmesi: mitigation matrisi tam uygulandığında olasılık veya etki skoru 1 birim azaltılır. Örnek:

```text
R-LGL-02 (FSEK): başlangıç 12 (Olasılık 3, Etki 4)
Mitigation tamamlandı:  6 (Olasılık 3 → 2 ✓, Etki 4 → 3 ✓)
```

Bu mekanik bir kural — risk-register §1.1'de standartlaştırılmış. Yeniden değerlendirme için "kabul kriteri" satırı her detaylı risk girişinde bulunur.

## Skor anomalileri (mevcut register'da tespit)

> ⚠️ **Tutarsızlık:** [docs/strategy/risk-register.md §2.1 ve §2.2](../../docs/strategy/risk-register.md):
>
> - **R-FIN-02 "DeepSeek API instability" skor 9** — §2.2 sarı tablosunda gösterilmiş; skor 9 → 🔴 olmalı.
> - **R-MKT-02 "ChatGPT yeter" skor 9** — §2.2 sarı tabloda; aynı sorun.
> - **R-MKT-03 "Düşük WTP" skor 9** — §2.2 sarı tabloda; aynı sorun.
>
> Aksiyon: Bu üç risk **kırmızıya taşınmalı** veya **skor revize** (Olasılık 3 → 2 sonuç 6 olur). `nodrat-dev` ile risk-register güncellenmeli. (Bu çelişki [[risk-register-md]] source sayfasında da not edildi.)

## İlişkiler

- **İlgili kavramlar:** [[mvp-cut-list-method]] (risk register MVP cut'ın nedenidir), [[kill-switch]] (risk geçişlerinde kill-switch kontrolü).
- **İlgili varlıklar:** [[risk-fsek-telif]], [[risk-kvkk-violation]], [[risk-source-fragility]], [[risk-cost-runaway]] — somut risk objeleri.
- **İlgili kararlar:** [[twenty-five-word-quote-cap]], [[pii-redaction-mandatory]] — risk mitigation locked decisions.
- **İlgili topics:** [[risk-catalog]] — 30 risk inventory.

## Açık sorular / TODO

- **Periyodik re-skor:** Risk skorları aylık güncelleniyor mu? "Mitigation tam uygulandı" doğrulamasını kim yapar (DPO? founder? otomatik kontroller?).
- **Yeşil → kırmızı eskalasyon prosedürü:** Yeşil bir risk siyah kuğu olayı sonrası kırmızıya çıkarsa hızlı re-evaluation runbook'u var mı?

## Kaynaklar

- [docs/strategy/risk-register.md §1 (metodoloji)](../../docs/strategy/risk-register.md)
- [docs/strategy/risk-register.md §2 (30 risk listesi)](../../docs/strategy/risk-register.md)
