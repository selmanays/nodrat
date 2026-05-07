---
type: concept
title: "Kill-switch (KS-1/KS-2/KS-3) — go/no-go gate'leri"
slug: "kill-switch"
category: "framework"
status: "live"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/strategy/risk-register.md§6"
  - "docs/strategy/risk-register.md§0"
tags: ["kill-switch", "mvp", "gate", "milestone", "decision"]
aliases: ["KS-1", "KS-2", "KS-3", "go-no-go"]
---

# Kill-switch — go/no-go gate'leri

> **TL;DR:** MVP-1 → MVP-2 → MVP-3 geçişlerinde 3 zorunlu kill-switch noktası. Her birinin **acceptance kriterleri** (geçerse devam) ve **no-go kriterleri** (durdurma/pivot) net. KS-2 özellikle "ürün-pazar fit acid testi" — D7 retention <%20 olursa pivot.

## Tanım

Kill-switch, ürün geliştirme metodolojisinde kullanılan "go/no-go decision point"tir. MVP'lerin sonunda (her milestone delivered olduğunda) ölçülebilir kriterler kontrol edilir; geçilmezse plan revize edilir veya proje durdurulur.

Nodrat'ta 3 ana KS noktası ve genel kill-switch'ler:

- **KS-1 — MVP-1 sonu (Hafta 12):** Çalışan minimum kabul edilebilir ürün. Teknik + hukuki + ön-validation odaklı.
- **KS-2 — MVP-2 sonu (Hafta 20):** Kullanılabilir SaaS. **Ürün-pazar fit acid testi** — D7 retention + NPS.
- **KS-3 — MVP-3 sonu (Hafta 28):** Ücretli launch. Conversion + WTP odaklı.
- **Genel:** 6 ay 50+ paid yoksa pivot; 12 ay MRR < cost ise kapatma; KVKK ihlal kapatma.

## Neden Nodrat'ta var

Üç motivasyon:

1. **Solo founder discipline.** R-PEO-01 (skor 12) için: subjektif "devam etmeli mi?" kararı yerine ölçülebilir kriter.
2. **Pivot timing.** Düşük retention ile "biraz daha iter, belki düzelir" yanılgısı yerine objektif çıkış noktası.
3. **Kapsam disiplini.** Her MVP geçişi cut-list ([[mvp-cut-list-method]]) ile birleşik — bir önceki KS geçildiyse sıradaki MVP scope'u onaylanır.

## KS-1 — MVP-1 sonu (Hafta 12)

```text
Acceptance kriterleri:
  [ ] 3 kaynak başarılı extraction ≥ %70 (R-OPS-01 mitigation)
  [✅] Discovery validation kanıtı (27 görüşme tamamlandı)
  [ ] Closed alpha 5+ kişi olumlu feedback
  [ ] LLM maliyeti tahmini margin uyumlu (< $0.01/gen)
  [ ] Halüsinasyon test seti < %5 false positive
  [✅] Avukat ToS/Privacy review yapılmış (legal-opinion-integration)

No-go kriterleri:
  - Extraction <%50 → kazıma altyapısı yeniden
  - User feedback "ChatGPT yetiyor" → discovery'e geri
  - Maliyet >$0.05/gen → provider strateji yeniden
```

**Durum (2026-05-07):** MVP-1 zaten production'da; bazı kriterler (✅) doğrulanmış, bazıları post-hoc kontrol bekliyor (extraction %, alpha feedback, halü test seti).

## KS-2 — MVP-2 sonu (Hafta 20) — ürün-pazar fit acid testi

```text
Acceptance kriterleri:
  [ ] Beta retention D7 ≥ %30
  [ ] Beta NPS ≥ 30
  [ ] 25 persona görüşmesi tamamlandı
  [ ] Selector test UI admin tarafından kullanılıyor
  [ ] 5+ kaynak aktif

No-go kriterleri:
  - D7 retention <%20 → ürün/persona uyumu yok, pivot
  - NPS <10 → kalite problemi
  - <5 kaynak çalışıyor → yapay zeka altyapı re-think
```

**Durum (2026-05-07):** MVP-2 ✅ delivered (-19 hafta erken). Ama KS-2 ölçümleri **MVP-3 cut-over'a taşındı** — issue'lar:

- #385 — alpha test (5-10 kişi closed beta, D7 retention)
- #386 — eval suite production runner (halü <%2)
- #387 — 25 persona görüşmesi
- #388 — load test sustained 50→200 RPS (k6 + p95)
- #389 — KS-2 final acceptance + release notes

Yani **KS-2 fiilen henüz açık** — code delivered ama acceptance ölçümleri devam ediyor.

## KS-3 — MVP-3 sonu (Hafta 28) — paid launch

```text
Acceptance kriterleri:
  [ ] Free → paid conversion ≥ %3
  [ ] Trial → free conversion ≥ %20
  [ ] Pro tier en az 5 paid user (mock onboarding)
  [ ] Cost per user < tier maliyet limiti

No-go kriterleri:
  - Conversion <%1 → pricing model yeniden
  - WTP <250 TL → tier/feature mix yeniden
```

**Durum (2026-05-07):** MVP-3 hedef 2026-11-30. Henüz launch yok.

## Genel kill-switch (proje yaşam döngüsü)

```text
- 6 ay içinde 50+ paid user yoksa → ürün-pazar fit yok, B2B pivot değerlendir
- 12 ay içinde MRR < cost (sustained) → kapatma değerlendir
- Yasal ihlal (KVKK Kurul kararı) → uyum sağlanmazsa kapatma
- Cyber breach (kullanıcı verisi sızıntı) → 30 gün uyum + bildirim
```

## Kill-switch ölçüm prosedürü

Her KS noktasında:

1. **Veri toplama** — kullanıcı analytics, financial, technical metrik'ler.
2. **Acceptance check** — her kriter check'lenir.
3. **No-go check** — pivot threshold'ları kontrol edilir.
4. **Karar** — 3 seçenekten biri:
   - **GO:** Sonraki MVP'ye geç.
   - **HOLD:** Bazı kriter eksik → eksik kriter için 2-4 hafta daha çalış, tekrar ölç.
   - **PIVOT:** No-go kriter tetiklendi → discovery/strategy/pricing/persona revize.
   - **STOP:** Genel kill-switch tetiklendi → projeyi durdur.

## İlişkiler

- **İlgili kavramlar:** [[mvp-cut-list-method]] (KS geçildikten sonra cut-list yenilenir), [[risk-scoring]] (KS no-go'lar genelde yüksek-skor risklerin gerçekleşmesi).
- **İlgili kararlar:** [[mvp-1-scope-lock]] (KS-1 sonrası MVP-2 scope kararı için temel).
- **İlgili topics:** [[mvp-roadmap]] (KS noktaları timeline'da).

## Açık sorular / TODO

- **KS-1 retro:** MVP-1 production'da, KS-1 acceptance check'i resmi olarak yapıldı mı? Hangi kriter ✅, hangi ❌? `nodrat-dev` ile retro issue açılmalı.
- **KS-2 timing:** MVP-2 -19 hafta erken delivered ama acceptance MVP-3 cut-over'a taşındı. KS-2 deadline yeniden ne? Persona görüşmeleri (#387) tamamlanmadan MVP-3 başlamalı mı?
- **Pivot scenarios:** "B2B pivot" net mi tanımlandı? Kim hedef? PRD/Discovery'de B2B segment yok — bu reaktif bir kararsa hangi ön-çalışma var?

## Kaynaklar

- [docs/strategy/risk-register.md §6 (kill-switch)](../../docs/strategy/risk-register.md)
- [docs/strategy/risk-register.md §0 (yönetici özeti — kill-switch noktaları)](../../docs/strategy/risk-register.md)
- [docs/strategy/success-metrics.md](../../docs/strategy/success-metrics.md) — KS-1 acceptance + KS-3 conversion KPI'ları
