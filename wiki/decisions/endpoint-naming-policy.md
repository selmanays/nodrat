---
type: decision
title: "Endpoint adlandırma politikası — milestone-bound ad yasak"
slug: "endpoint-naming-policy"
status: "locked"
decided_on: "2026-05-08"
decided_by: "founder"
created: "2026-05-08"
updated: "2026-05-08"
sources:
  - "GitHub Issue #432 (mvp-2-1-delta — kötü örnek)"
  - "GitHub Issue #440 (refactor → pipeline-comparison)"
  - "GitHub PR #441"
tags: ["locked-decision", "api", "convention", "engineering"]
aliases: ["api-naming", "endpoint-naming", "production-endpoint-naming"]
---

# Endpoint adlandırma politikası

> **Karar:** Production endpoint URL'leri **milestone, sprint, epic veya issue numarası** içeremez. Endpoint adı **ne yaptığını** anlatmalı, **ne zaman yazıldığını** değil. Aksi takdirde bir-iki çeyrek sonra ad anlamsızlaşır ve refactor borcu olur.
> **Durum:** locked.
> **Tarih:** 2026-05-08 (PR [#441](https://github.com/selmanays/nodrat/pull/441) ile uygulandı).

## Bağlam

[#432](https://github.com/selmanays/nodrat/issues/432) ile geçici bir performans ölçüm aracı olarak `GET /admin/dashboard/mvp-2-1-delta` endpoint'i yazıldı. Acceptance kriterlerini karşılamak için hızlı bir araç gerekiyordu, isim "MVP-2.1 epic close-out" bağlamından alındı.

Kullanıcı haklı bir eleştiri getirdi:
> "mvp-2-1-delta amatörce bir isim değil mi?"

Eleştirinin maddi yönleri:
- **Milestone-bound:** MVP-2.1 bittiğinde isim referans verdiği context'i kaybeder.
- **İç jargon:** "delta" matematiksel fark — yeni geliştirici için boş.
- **Tek-amaçlı:** Yalnızca tek bir tarih karşılaştırması için yazılmıştı, oysa aynı ölçüm aracı her optimizasyon dalgasından sonra (MVP-3.x, ileride 4.x) tekrar tekrar lazım olur.

Bu vakaya bakınca aynı hatayı yapmamak için kalıcı bir kural koymak gerekti.

## Karar detayı

```text
✅ KABUL: Endpoint adı eylemi/işlevi anlatır
   /admin/rag/pipeline-comparison
   /admin/sources/{id}/test-listing
   /admin/queue/failed
   /app/billing/checkout

🛑 RED: Endpoint adı sürüm/sprint/epic kodunu içerir
   /admin/dashboard/mvp-2-1-delta        ← #432, refactor edildi #441
   /admin/rag/v2-rerank                  ← geleceğin tuzağı
   /admin/dashboard/q3-cost-report       ← çeyrek-bound

🛑 RED: Endpoint adı issue/PR numarasını içerir
   /admin/dashboard/issue-432-fix
   /api/internal/pr-411-debug
```

### Kapsam

- **Production endpoint'leri** (auth + DB hit + audit logged) bu kurala uyar.
- **Internal/debug endpoint'leri** (geçici, feature-flagged) milestone içerebilir ama merge öncesi yeniden adlandırılmalı veya rollback edilmeli.
- **Test/eval endpoint'leri** (`/admin/eval/*`, `/internal/test/*`) bu kuralın istisnası — context'leri zaten geçici.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Tüm endpoint'ler tarih-bağlı (örn. `/admin/dashboard/2026-q2-perf`) | İlk PR hızlı | Her çeyrek refactor borcu, isim spam | Reddedildi |
| Milestone-bound endpoint'ler (örn. `/mvp-2-1-delta`) | Issue ile birebir eşleşme | Bağlamsız 6 ay sonra | Reddedildi (bu vakanın sebebi) |
| Sürüm prefix'i (örn. `/v2/...`) | API evolution kolay | URL şişer, mevcut Caddy reverse proxy'de gerek yok | Reddedildi (MVP-1.x için fazla) |
| **Eylem-bazlı isim (`/pipeline-comparison`, `/test-listing`)** | Kalıcı, sürdürülebilir, jenerik | İlk yazımda biraz daha düşünmek gerekir | **Seçildi** |

## Sonuçlar

- **Etkilenen mevcut endpoint'ler:** Yok (#432 dışında milestone-bound endpoint yoktu — proaktif kural). Mevcut endpoint isimleri [`docs/engineering/api-contracts.md`](../../docs/engineering/api-contracts.md) §0'da listelenir, hepsi bu kurala uygun.
- **Etkilenen yeni endpoint'ler:** Bu kuraldan sonra eklenen endpoint'ler PR review'da ad kontrolünden geçer.
- **Etkilenen sayfalar:** [[mvp-roadmap]] (MVP isimlendirme convention), [[pipeline-performance-baseline]] (yeni endpoint adı yansıtıldı).
- **Etkilenen kod:** `apps/api/app/api/admin_rag.py` (yeni endpoint), `apps/api/app/api/admin_dashboard.py` (eski endpoint silindi).
- **Etkilenen dokümanlar:**
  - [docs/engineering/api-contracts.md §10.4](../../docs/engineering/api-contracts.md) — yeni endpoint sözleşmesi
  - [INDEX.md §4](../../INDEX.md) — kararlar listesi
  - [INDEX.md §7 (Konvansiyonlar)](../../INDEX.md) — konvansiyonlar listesine eklenecek (ayrı PR)

## Geri alma maliyeti

Düşük. Bu bir code-review kuralıdır, kod değil. Yeni bir milestone-bound endpoint eklenmek istenirse PR'da yakalanır ve refactor istenir. Mevcut endpoint'ler etkilenmez.

## Uygulama

1. **PR review checklist'i** (mevcut review template'lerine eklenecek): "Endpoint adı milestone/sprint/epic kodu içeriyor mu?"
2. **CI lint kuralı (önerilebilir):** OpenAPI schema'da path'leri tarayıp `mvp-`, `sprint-`, `epic-`, `q[1-4]-`, `v[0-9]-` regex'leriyle eşleşen path varsa fail. Şu an manuel kontrol yeterli.
3. **api-contracts.md §0'a not düşülecek:** "Bu kural production endpoint'leri için locked'dır."

## İlişkiler

- **Bağlı varlıklar:** —
- **Bağlı kavramlar:** [[provider-abstraction]] (interface stability prensibi)
- **Bağlı kararlar:** [[pipeline-observability-location]]
- **Bağlı topics:** [[mvp-roadmap]], [[pipeline-performance-baseline]]
- [[shadcn-customization-policy]]

## Kaynaklar

- [GitHub Issue #432](https://github.com/selmanays/nodrat/issues/432) — mvp-2-1-delta endpoint (kötü örnek)
- [GitHub Issue #440](https://github.com/selmanays/nodrat/issues/440) — refactor → pipeline-comparison
- [GitHub PR #441](https://github.com/selmanays/nodrat/pull/441) — uygulama
- [docs/engineering/api-contracts.md §10.4](../../docs/engineering/api-contracts.md) — yeni jenerik endpoint
- [INDEX.md §4 (Çekirdek kararlar — locked)](../../INDEX.md)
