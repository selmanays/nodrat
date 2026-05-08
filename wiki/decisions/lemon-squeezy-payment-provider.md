---
type: decision
title: "Lemon Squeezy payment provider (Merchant of Record, USD primary)"
slug: "lemon-squeezy-payment-provider"
status: live
created: 2026-05-08
updated: 2026-05-08
sources:
  - "GitHub Epic #448"
  - "docs/strategy/pricing-strategy.md§6"  # docs catch-up beklenir (Epic #448 docs PR)
tags: [payment, billing, mvp-3, locked-decision, mor, lemon-squeezy]
aliases: [ls, lemonsqueezy, mor]
---

# Lemon Squeezy payment provider (MoR)

> **TL;DR:** Faz 6 ödeme stack'i Iyzico'dan **Lemon Squeezy (Merchant of Record)**'e geçiyor. LS satıcı sıfatıyla fatura keser, global tax compliance'ı yönetir, payout'u Nodrat'a (şahıs banka hesabına) gönderir. Bu sayede **ilk lansman için Limited Şti. kuruluşu gereksiz**, e-Arşiv yükümlülüğü Nodrat'tan LS'ye geçer. Para birimi **USD primary** (TL display locale ile). Karar 2026-05-08 — solo founder + bootstrap context'te launch hızı önceliklendirildi.

## Karar

```text
✅ Default payment provider:  Lemon Squeezy (lemonsqueezy.com)
✅ Provider rolü:              Merchant of Record (MoR)
✅ Para birimi:                USD primary, TL display locale ile
✅ Şirket gereksinimi:         İlk aşamada YOK (LS MoR sıfatıyla satar)
✅ Fatura:                     LS keser müşteriye (KDV global handling)
✅ Trial:                      Card-required, LS native trial period (3-7 gün)
✅ Multi-seat (Agency):        LS variant + custom seat counter (Nodrat side)
✅ Refund/chargeback:          LS hosted yönetir (Nodrat müdahale yok)
✅ Customer portal:            LS hosted (cancel, update card, invoice list)
🛑 Iyzico:                     Kaldırıldı
🛑 PayTR:                      Kaldırıldı (TR alternatifi olarak da değerlendirilmedi)
🛑 Stripe direct:              Kaldırıldı (MoR değil; TR Inc gerekirdi)
🛑 e-Arşiv (TR):               Kaldırıldı (LS MoR fatura keser)
🛑 Limited Şti. (#46):         Defer (>$3K MRR sonrası yeniden değerlendir)
```

## Bağlam

Önceki plan (Iyzico) iki yapısal şart dayatıyordu:

1. **Limited Şti. kuruluşu** — Iyzico merchant olmak için tüzel kişilik şart (~6-8 hafta süreç + sermaye + muhasebe).
2. **e-Arşiv fatura altyapısı** — TR satıcı sıfatıyla her aboneliğe Nodrat e-Arşiv kesmek zorunda (yazılım + integratör + muhasebe).

Solo founder + bootstrap context'te bu iki şart **launch'u 2-3 ay erteler** ve aylık ~$50-100 sabit maliyet ekler. Lemon Squeezy MoR modeli bu engelleri ortadan kaldırır — LS Türk müşteriye **kendi adına** fatura keser, Nodrat'a payout **affiliate-style net revenue** olarak gönderir; Nodrat sadece TR gelir vergisi beyanına dahil eder (vergi danışmanı işi).

| Boyut | Iyzico | Lemon Squeezy (MoR) |
|---|---|---|
| Hukuki rol | Payment processor — Nodrat satıcıdır | MoR — LS satıcıdır, Nodrat affiliate gibi payout alır |
| Şirket gereksinimi | Limited Şti. zorunlu | Yok (şahıs payout) |
| Fatura | Nodrat e-Arşiv keser | LS müşteriye fatura keser |
| Para birimi | TL primary | USD primary |
| Komisyon | ~%2.5 | ~%5 + 50¢ |
| Veri akışı | TR içi | ABD'ye PII transfer (KVKK m.9) |
| Refund/chargeback | Nodrat yönetir | LS yönetir |
| Customer portal | Custom build | LS hosted |
| TR dışı pazara açılma | Ek altyapı | Hazır (geo-disable çıkarsa global) |

## Trade-off'lar

**Kazanılan:**
- **Launch hızı** — Limited Şti. süreci ~6-8 hafta yok
- **Sabit maliyet sıfıra yakın** — e-Arşiv altyapı ~$30/ay yazılım + ~$50/ay muhasebe yok
- **Tax compliance global** — KDV, VAT, US sales tax LS yönetir
- **Refund/chargeback operational yük yok** — LS portal hosted
- **TR dışı pazara açılma kolay** — global out of the box
- **Customer portal hazır** — solo founder için custom UI gereksiz

**Kaybedilen / kabul edilen:**
- **Komisyon ~%2.5 daha yüksek** — Pro $24 → $24 - $1.20 - $0.50 ≈ $22.30 net (~%93 retain)
- **TR müşteri ödeme deneyimi USD görür** — FX riski algısı (gerçek FX dalgalanmasını LS soğurur)
- **LS hesap kapatma/payout gecikme riski** — yeni risk: R-FIN-XX (MoR dependency)
- **KVKK m.9 yurt dışı transfer açık rıza zorunluluğu** — yeni issue [#453](https://github.com/selmanays/nodrat/issues/453)
- **TRY native değil** — kullanıcı kart USD charge edilir; bankadan TL hesabı varsa FX banka uygular

## Alternatifler

| Provider | MoR? | TRY native? | Şirket gerekli? | Reddetme nedeni |
|---|---|---|---|---|
| **Iyzico** | Hayır | Evet | Evet | Şirket + e-Arşiv launch geciktirir (8+ hafta) |
| **PayTR** | Hayır | Evet | Evet | Aynı gerekçe |
| **Stripe direct** | Hayır | Hayır | Evet (TR Inc çok zor) | TR satıcı için sınırlı, MoR yok |
| **Stripe Atlas (US Inc + Stripe)** | Hayır | Hayır | Evet (US Inc, $500+ kuruluş + KOB üyelik) | Maliyet + karmaşıklık yüksek; pivot opsiyonu olarak ileri tut |
| **Paddle** | Evet | Hayır | Hayır | LS muadili; biraz daha pahalı (~%5+50¢, benzer); enterprise odaklı, solo founder UX zayıf |
| **Lemon Squeezy** | **Evet** | Hayır | **Hayır** | ✅ Seçilen — solo founder odaklı UX, hızlı setup, global ready |

## İlişkiler

- **İlgili decisions:** [[mvp-1-scope-lock]] (MVP-3 scope etkilenir — Faz 6 ödeme satırı LS olacak)
- **İlgili topics:** [[mvp-roadmap]] (MVP-3 kapsamı), [[risk-catalog]] (yeni R-FIN-XX MoR dependency, R-FIN-XX FX exposure, R-LGL-XX KVKK m.9)
- **İlgili concepts:** [[provider-abstraction]] (LS payment provider interface — Faz 6+ providers tablosu)

## Açık sorular / TODO

- **Vergi beyanı süreci:** Şahıs olarak LS payout'unu TR gelir vergisi beyanına ekleyeceksin (vergi danışmanı işi — `nodrat-dev` scope dışı).
- **Avukat review:** ToS/Privacy/KVKK aydınlatma metinleri LS için güncellenmeli (Epic #448 docs PR + #453 ile takip).
- **MRR threshold ne olmalı?** Hangi MRR seviyesinde Limited Şti. kuruluşu yeniden değerlendirilecek? Geçici plan: **>$3K/ay**. Kullanıcının vergi danışmanı görüşü daha uzun vadeli net rakam verecek.
- **TR FX hedging gerek mi?** Müşteri USD görür, ödeme USD; ama Nodrat masrafları TL (VPS Contabo €/ay, operasyon TL). USD payout'tan TL'ye dönüşüm bankada — FX strategy ihtiyacı küçük revenue'da yok, MRR >$1K'da değerlendir.
- **LS DPA + SCC imzalı mı?** [#49](https://github.com/selmanays/nodrat/issues/49) güncellendi. KVKK m.9 + AB GDPR için SCC dosyası arşivde tutulmalı.

## Kaynaklar

- [GitHub Epic #448](https://github.com/selmanays/nodrat/issues/448) — Iyzico → LS pivot (master tracking)
- [Sub-issue #53](https://github.com/selmanays/nodrat/issues/53) — Faz 6 LS entegrasyonu (rename + body update)
- [Sub-issue #76](https://github.com/selmanays/nodrat/issues/76) — /app/billing UI (LS checkout/portal)
- [Sub-issue #450](https://github.com/selmanays/nodrat/issues/450) — LS Customer Portal + webhook handler
- [Sub-issue #451](https://github.com/selmanays/nodrat/issues/451) — Multi-seat agency LS variant
- [Sub-issue #453](https://github.com/selmanays/nodrat/issues/453) — KVKK m.9 yurt dışı transfer açık rıza
- [#46 closed](https://github.com/selmanays/nodrat/issues/46) — Limited Şti. defer
- docs/strategy/pricing-strategy.md §6 — geographic pricing (docs PR sonrası catch-up)
- docs/product/prd.md §6 — Faz 6 (docs PR sonrası catch-up)
