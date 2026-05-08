---
type: decision
title: "Lemon Squeezy payment provider (Merchant of Record, USD primary)"
slug: "lemon-squeezy-payment-provider"
status: live
review_status: avukat-sartli-onayli + vergi-danismani-integrated  # 2026-05-08
created: 2026-05-08
updated: 2026-05-08
sources:
  - "GitHub Epic #448"
  - "docs/strategy/pricing-strategy.md§6"
  - "docs/legal/opinion-integration.md§3.9"   # avukat 6 cevap
  - "docs/legal/opinion-integration.md§3.10"  # vergi danışmanı 7 madde
  - "docs/legal/refund-policy.md"             # avukat şartlı onayı output
  - "docs/legal/mesafeli-satis-sozlesmesi.md" # avukat şartlı onayı output
  - "docs/legal/payment-fallback-plan.md"     # avukat R-FIN-04 output
tags: [payment, billing, mvp-3, locked-decision, mor, lemon-squeezy, avukat-onayli, vergi-danismani-onayli]
aliases: [ls, lemonsqueezy, mor]
---

# Lemon Squeezy payment provider (MoR)

> **TL;DR:** Faz 6 ödeme stack'i Iyzico'dan **Lemon Squeezy (Merchant of Record)**'e geçiyor. LS satıcı sıfatıyla fatura keser, global tax compliance'ı yönetir, payout'u Nodrat'a (şahıs banka hesabına) gönderir. Bu sayede **ilk lansman için Limited Şti. kuruluşu gereksiz**, e-Arşiv yükümlülüğü Nodrat'tan LS'ye geçer. Para birimi **USD primary** (TL display locale ile). Karar 2026-05-08 — solo founder + bootstrap context'te launch hızı önceliklendirildi. **Avukat şartlı onaylı** (7 ön-launch maddesi) + **Vergi danışmanı integrated** (şahıs ticari kazanç mükellefiyeti, threshold $5K MRR plan / $10K convert).

## Review status (2026-05-08)

```text
✅ Avukat: ŞARTLI UYGUN — Epic #448 §3.9 N-09 RESOLVED
   "LS MoR launch için makul ve yönetilebilir risk; hukuken tamamen
    risksiz değil. 7 ön-launch maddesi listelendi."
   Output: refund-policy.md, mesafeli-satis-sozlesmesi.md,
           payment-fallback-plan.md (3 yeni canonical doc)
   Pending: avukat final review (DRAFT legal/* için)

✅ Vergi danışmanı: ONAYLI — Epic #448 §3.10 N-10 INTEGRATED
   "TR müşteriye Nodrat e-Arşiv kesmemeli; LS payout şahıs ticari
    kazanç olarak sınıflandırılır. Threshold: $3K review / $5K plan
    / $10K convert."
   Output: unit-economics.md §8.1 threshold matrisi + §8.2 muhasebe
           akışı, opinion-integration.md §3.10
   Pending: mali müşavirden 4 yazılı teyit (#473)
```

## Implementation status (2026-05-09 — KS-2 sonrası backend kick-off)

```text
✅ Backend altyapısı production'da (3 PR, scaffold mode)

#470 KVKK m.9 server-side gate         ✅ MERGED + DEPLOYED + 5/5 PASS (PR #492)
   ─ 4 nullable TIA sütunu (version + IP + text_hash + revoked_at)
   ─ require_foreign_transfer_consent dependency (5 akışta uygulanır)
   ─ /app/consent/{status, foreign-transfer POST/DELETE} endpoints
   ─ POST /app/generate gate (LLM çağrısı bloklanır consent yoksa)

#56 Admin 2FA TOTP                      ✅ MERGED + 2 hotfix + 5/5 PASS (PR #493/494/495)
   ─ pyotp 2.9.0 + JSONB backup_codes (10 SHA-256, one-time use)
   ─ /auth/2fa/{status, setup, verify-setup, verify-challenge,
     disable, regenerate-backup}
   ─ Login flow: TwoFactorChallengeResponse union; totp_enabled
     ise 5-dk challenge token → verify-challenge → tam session
   ─ R-SEC-01 mitigation aktif

#53 LS billing scaffold                 ✅ MERGED + 5/5 PASS (PR #497)
   ─ 5 yeni tablo: plans, subscriptions, invoices, agency_seats,
     webhook_events
   ─ 6 plan seed (USD primary, ls_variant_id_* NULL placeholder)
   ─ LemonSqueezyProvider (httpx JSON:API + HMAC SHA256 sig verify)
   ─ /app/billing/{plans, checkout, subscription, portal-url,
     invoices, seats, seats/invite, seats/{id}}
   ─ /api/webhooks/lemonsqueezy (idempotent + 7 event tipi)
   ─ Scaffold mode: LS env yok → 503 BILLING_NOT_CONFIGURED graceful
   ─ #470 KVKK m.9 gate checkout + portal-url'a uygulandı

⏳ Frontend implementation (sırada):
   #453 KVKK m.9 frontend modal (Next.js — /app/consent UX)
   #76  /app/billing UI (plans/checkout/subscription/invoices/manage)
   #77  /admin/plans UI (variant_id atama)
   #450 Multi-seat Agency UI (invite/list/remove)
   #52  Stil profili Faz 5 A/B test (Pro tier upsell)

⏳ Kullanıcı manuel (paralel):
   #487 Avukat final review (legal/* DRAFT — backlog)
   #473 Mali müşavir + şahıs ticari kazanç (backlog)
   #471 Paddle yedek hesap (R-FIN-04 — backlog, opsiyonel)
   LS hesap KYC + product/variant tanımı (backlog)
```

**LS hesap aktive sonrası:** kod değişikliği YOK. Sadece `.env`'de 13 placeholder doldurulur (API key + store + signing secret + 10 variant_id) → `plans` tablosu UPDATE ile `ls_variant_id_*` doldurulur (veya #77 admin UI ile) → `docker compose restart api worker_*` → checkout 200 dönmeye başlar.

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
- **LS hesap kapatma/payout gecikme riski** — R-FIN-04 (skor 9 🔴, avukat onaylı 6-senaryo aksiyon matrisi `payment-fallback-plan.md`'de + Paddle ön başvuru #471)
- **KVKK m.9 yurt dışı transfer açık rıza zorunluluğu** — frontend [#453](https://github.com/selmanays/nodrat/issues/453) + backend server-side enforcement [#470](https://github.com/selmanays/nodrat/issues/470) (avukat: server-side zorunluya yakın)
- **TIA (Transfer Impact Assessment) kayıt yükü** — avukat şartlı onayı: DPA+SCC tek başına yeterli değil; 5 maddelik TIA `kvkk-aydinlatma.md §4.2.1` + `ropa.md §16.1`
- **TRY native değil** — kullanıcı kart USD charge edilir; bankadan TL hesabı varsa FX banka uygular
- **Mali müşavir 4 yazılı teyit yükü** — vergi danışmanı: LS reverse invoice yeterli mi, KDV ihracat istisnası, sınıflandırma, FX kayıt netliği ([#473](https://github.com/selmanays/nodrat/issues/473))

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
- **İlgili topics:** [[mvp-roadmap]] (MVP-3 kapsamı), [[risk-catalog]] (yeni R-FIN-04 MoR dependency, R-FIN-05 FX exposure, R-LGL-13 KVKK m.9)
- **İlgili concepts:** [[provider-abstraction]] (LS payment provider interface — Faz 6+ providers tablosu)

## Resolved sorular (2026-05-08 — Avukat + Vergi Danışmanı)

- ✅ **Vergi beyanı süreci** → vergi danışmanı: **şahıs ticari kazanç** mükellefiyeti aç ("Yazılım/SaaS dijital ürün geliri — yurtdışı MoR payout"). Mali müşavirden 4 yazılı teyit alınacak ([#473](https://github.com/selmanays/nodrat/issues/473)).
- ✅ **Avukat review** → şartlı uygun. 7 ön-launch maddesi listelendi (`opinion-integration.md §3.9 N-09 RESOLVED`). Final review legal/* DRAFT için yayın öncesi alınacak.
- ✅ **MRR threshold (Limited Şti.)** → vergi danışmanı resmi pozisyonu: **\$3K MRR review** / **\$5K MRR plan başlat** / **\$10K MRR convert kuvvetle önerilir**. B2B/ajans satışları artarsa MRR'den bağımsız Limited.
- ✅ **TR FX hedging** → vergi danışmanı: ticari faaliyet kapsamında kur farkı geliri/gideri olarak izle (TCMB döviz alış / muhasebe kuru). >\$1K MRR'de profesyonel FX strategy değerlendir (R-FIN-05 mitigation).
- ✅ **LS DPA + SCC + TIA** → avukat şartlı onayı: DPA + SCC tek başına yeterli değil; ek TIA (Transfer Impact Assessment) 5 maddelik kayıt sistemi gerekli (`kvkk-aydinlatma.md §4.2.1` + `ropa.md §16.1`). LS subprocessor list arşivlenecek ([#49](https://github.com/selmanays/nodrat/issues/49)).

## Açık implementation TODO

- [ ] [#470](https://github.com/selmanays/nodrat/issues/470) Server-side foreign_transfer_consent enforcement (5 akış 403 gate)
- [ ] [#471](https://github.com/selmanays/nodrat/issues/471) Paddle fallback hesap + PaymentProvider abstraction (R-FIN-04)
- [ ] [#472](https://github.com/selmanays/nodrat/issues/472) refund-policy + mesafeli-satis frontend yayını
- [ ] [#473](https://github.com/selmanays/nodrat/issues/473) Şahıs ticari kazanç mükellefiyeti aç + mali müşavir 4 yazılı teyit + kontrat

## Kaynaklar

- [GitHub Epic #448](https://github.com/selmanays/nodrat/issues/448) — Iyzico → LS pivot (master tracking, review-resolved)
- [Sub-issue #53](https://github.com/selmanays/nodrat/issues/53) — Faz 6 LS entegrasyonu (rename + body update)
- [Sub-issue #76](https://github.com/selmanays/nodrat/issues/76) — /app/billing UI (LS checkout/portal)
- [Sub-issue #450](https://github.com/selmanays/nodrat/issues/450) — LS Customer Portal + webhook handler
- [Sub-issue #451](https://github.com/selmanays/nodrat/issues/451) — Multi-seat agency LS variant
- [Sub-issue #453](https://github.com/selmanays/nodrat/issues/453) — KVKK m.9 yurt dışı transfer açık rıza (frontend)
- [Sub-issue #470](https://github.com/selmanays/nodrat/issues/470) — Server-side foreign_transfer_consent enforcement (backend)
- [Sub-issue #471](https://github.com/selmanays/nodrat/issues/471) — Paddle fallback PaymentProvider abstraction (R-FIN-04)
- [Sub-issue #472](https://github.com/selmanays/nodrat/issues/472) — refund-policy + mesafeli-satis frontend yayın
- [Sub-issue #473](https://github.com/selmanays/nodrat/issues/473) — Şahıs ticari kazanç mükellefiyeti + mali müşavir
- [#46 closed](https://github.com/selmanays/nodrat/issues/46) — Limited Şti. defer (vergi danışmanı eşiği: $5K MRR plan / $10K convert)
- [Sub-issue #49](https://github.com/selmanays/nodrat/issues/49) — Provider DPA listesi (LS DPA + SCC + subprocessor)
- docs/strategy/pricing-strategy.md §6 — geographic pricing
- docs/product/prd.md §6 — Faz 6
- **docs/legal/refund-policy.md** — LS hosted refund + 14 gün cayma (yeni canonical)
- **docs/legal/mesafeli-satis-sozlesmesi.md** — TR Mesafeli Sözleşmeler Yönetmeliği uyumu (yeni canonical)
- **docs/legal/payment-fallback-plan.md** — R-FIN-04 6-senaryo aksiyon matrisi + Paddle ön başvuru (yeni canonical)
- **docs/legal/opinion-integration.md §3.9 + §3.10** — avukat 6 cevap + vergi danışmanı 7 madde detay
- **docs/strategy/unit-economics.md §8.1 + §8.2** — şahıs ticari kazanç threshold matrisi + LS payout muhasebe akışı
