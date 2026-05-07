---
type: decision
title: "25-kelime direct quote hard cap (FSEK)"
slug: "twenty-five-word-quote-cap"
status: "locked"
decided_on: "2026-05-01"
decided_by: "legal"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/strategy/risk-register.md§3.1"
  - "docs/strategy/risk-register.md§2.1"
  - "INDEX.md§4"
  - "docs/legal/compliance-brief.md§3"
tags: ["locked-decision", "legal", "fsek", "copyright", "output-rule"]
aliases: ["quote-cap", "fsek-quote-rule", "25-word-rule"]
---

# 25-kelime direct quote hard cap

> **Karar:** Nodrat'ın ürettiği her output'ta (X post, summary, headline, vb.) kaynak makaleden alınan **direct quote 25 kelimeyi geçemez**. Sistem-level hard cap; LLM prompt + post-process validator çift güvenlik.
> **Durum:** locked.
> **Tarih:** 2026-05-01 (risk-register.md v0.1 yayını + Legal Brief §3'te detaylı).

## Bağlam

R-LGL-02 (FSEK telif tazminat, skor 12 — proje genelindeki **en yüksek tek risk**) için **birincil mitigation** budur. Türkiye'de 5846 sayılı Fikir ve Sanat Eserleri Kanunu (FSEK) iktibas (alıntı) sınırını net bir kelime sayısıyla tanımlamasa da:

- **§35 iktibas hakkı:** "amaçla mütenasip" sınırlı alıntı hak.
- **Pratik:** Yargıtay içtihadı 25-50 kelime aralığında "kısa iktibas" kabul eder; üzeri "yeniden yayın" sayılabilir.

Karar 25-kelime hard cap'i seçti — alt sınır, en güvenli noktada. Bu hem Yargıtay içtihadına uyumlu hem de LLM output'unda enforce edilebilir mekanik bir kural.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| 50-kelime cap | Daha esnek output | Yargıtay sınırına yakın, risk yüksek | Reddedildi (margin için 25 daha güvenli) |
| Yüzde-bazlı (%10 makale) | Adaptif | Kısa makalede hala büyük alıntı, mekanik enforce zor | Reddedildi |
| Quote yasağı (0 kelime) | Sıfır risk | Output kalitesi düşer, citation imkânsız | Reddedildi |
| Sadece prompt kuralı | Kolay implementasyon | LLM uymayabilir, post-process validator yok | Reddedildi (çift güvenlik şart) |
| Tam metin reproduction (kontrolsüz) | — | R-LGL-02 tetikleyicisi — tazminat 50K-1M TL | Reddedildi (felaket senaryosu) |

## Çift güvenlik mekanizması

```text
1. SYSTEM PROMPT katmanı:
   - "Direct quote ≤25 kelime; kaynak gösterimi zorunlu"
   - prompt-contracts.md'de tek tek prompt'larda tekrarlanır

2. POST-PROCESS validator katmanı:
   - Generation çıktısı tokenize edilir
   - Kaynak makale ile longest-common-substring/n-gram tespit
   - 25+ kelime contiguous quote → block + retry (insufficient_data fallback)
```

Detay: [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) ve [docs/strategy/risk-register.md §3.1](../../docs/strategy/risk-register.md) §3.1 mitigation matrisi M1-M7.

## Sonuçlar

- **Etkilenen kavramlar:** [[risk-fsek-telif]] (bu mitigation oraya bağlı), citation framework.
- **Etkilenen varlıklar:** Tüm LLM output'ları ([[deepseek-v3]], [[claude-haiku-4-5]] kanalları).
- **Etkilenen kararlar:** [[mvp-1-scope-lock]] (bu kural MVP-1'den itibaren aktif).
- **Etkilenen kod:** `apps/api/app/services/output_validator.py` — quote detector + retry logic.
- **Etkilenen dokümanlar:**
  - [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) — system prompt rules
  - [docs/legal/tos.md](../../docs/legal/tos.md) — kullanıcı sorumluluk maddesi
  - [docs/legal/compliance-brief.md §3](../../docs/legal/compliance-brief.md) — FSEK detay
  - [INDEX.md §4](../../INDEX.md) — locked decision listesinde

## Geri alma maliyeti

Bu kararı değiştirmek (örn. 50 kelimeye çıkarmak):

1. **Hukuki risk yeniden değerlendirme** — avukat görüşü, içtihat tarama.
2. **Validator threshold update** — kod 1 satır.
3. **Prompt-contracts revize** — 3 prompt güncellenmeli.
4. **Eval test set re-baseline** — golden test'lerin output kelime sayıları yeni sınırla regresyon yapmamalı.
5. **ToS sürüm bump** — kullanıcılara bildirim.

Tahmini değişiklik süresi: 1 hafta. **Ama yapılması ÖNERİLMİYOR** — risk-register §3.1 mitigation matrisi M1 bu kuralın merkezi.

## Kontrol checkpoint'leri

risk-register §3.1'den:

```text
- Faz 1 sonu:    Avukat review kılavuzu uygulanıyor mu
- Faz 3 sonu:    100 örnek output review (telif riski)
- Aylık:         Kaynak başına direct quote oranı raporu
```

Output validator otomatik enforce ediyor → manuel review yedek katman.

## İlişkiler

- **Bağlı varlıklar:** [[risk-fsek-telif]] (bu kararın motivasyonu)
- **Bağlı kavramlar:** [[risk-scoring]]
- **Bağlı kararlar:** —
- **Bağlı topics:** [[risk-catalog]]

## Kaynaklar

- [docs/strategy/risk-register.md §3.1](../../docs/strategy/risk-register.md) — R-LGL-02 detay + mitigation matrisi
- [docs/strategy/risk-register.md §2.1](../../docs/strategy/risk-register.md) — risk skoru
- [docs/legal/compliance-brief.md §3](../../docs/legal/compliance-brief.md) — FSEK detay
- [docs/legal/tos.md](../../docs/legal/tos.md) — kullanıcı sorumluluk
- [INDEX.md §4](../../INDEX.md) — Çekirdek kararlar
