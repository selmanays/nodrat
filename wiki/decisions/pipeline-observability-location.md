---
type: decision
title: "Pipeline observability yeri — /admin/rag (LLM/RAG), /admin/observability (infra)"
slug: "pipeline-observability-location"
status: "locked"
decided_on: "2026-05-08"
decided_by: "founder"
created: "2026-05-08"
updated: "2026-05-08"
sources:
  - "GitHub Issue #440"
  - "GitHub PR #441"
  - "apps/web/src/app/admin/rag/page.tsx"
  - "apps/web/src/app/admin/observability/page.tsx"
tags: ["locked-decision", "ui", "observability", "admin-panel"]
aliases: ["pipeline-monitoring-location", "rag-observability-location", "admin-panel-layout"]
---

# Pipeline observability yeri

> **Karar:** Nodrat admin panelinde **iki ayrı gözlem sayfası** vardır ve sorumlulukları net ayrılır:
>
> - **`/admin/observability`** = **Altyapı gözlem.** VPS, Postgres, MinIO, Contabo Object Storage, Backup. "Sistem Durumu" sayfası.
> - **`/admin/rag`** = **LLM/RAG pipeline gözlem.** Sağlık, Atıf, Yeniden Sıralama, RAPTOR, İnceleyici, Performans (#440). "RAG İzlencesi" sayfası.
>
> Yeni bir LLM-pipeline metric aracı yazılırsa **`/admin/rag` sayfasına yeni sekme** olarak eklenir, yeni sayfa açılmaz.
> **Durum:** locked.
> **Tarih:** 2026-05-08 (PR [#441](https://github.com/selmanays/nodrat/pull/441) Performans sekmesiyle uygulandı).

## Bağlam

[#432](https://github.com/selmanays/nodrat/issues/432)'de yazılan `/admin/dashboard/mvp-2-1-delta` endpoint'i UI'sız bırakılmıştı (browser console'dan auth header ile çağrılması gerekiyordu — pratik değil).

[#440](https://github.com/selmanays/nodrat/issues/440) ile UI eklenmesi planlandı. İki seçenek vardı:

1. **`/admin/observability` (Sistem Durumu)** sayfasına yeni kart/sekme: orada zaten "Sistem Durumu" başlığı var, fakat içerik tamamen **infrastructure** (VPS RAM/CPU/disk, DB boyutu, MinIO bucket'lar, backup snapshot'ları). Pipeline metrikleri (token, latency, cache hit, halü) ekleme orijinal niyetle çelişir — sayfa "sistem altyapısı"ndan "her şey karışık" hale gelir.
2. **`/admin/rag` (RAG İzlencesi)** sayfasına yeni sekme: orada zaten 6 sekme var (Sağlık / Karşılaştırma / Atıf / Yeniden Sıralama / RAPTOR / İnceleyici), hepsi LLM/RAG pipeline gözlemi. Yeni "Performans" sekmesi doğal olarak buraya uyar.

İkinci seçenek seçildi. Bu kararı kalıcı hale getirmek için bir locked decision olarak yazılır — gelecekte benzer ikilemde (örn. cost dashboard, prompt eval, citation accuracy aging) aynı kural uygulanır.

## Karar detayı

```text
/admin/observability  →  ALTYAPI gözlem
   - VPS health (CPU / RAM / disk)
   - PostgreSQL boyut + tablo
   - MinIO bucket boyutları
   - Contabo Object Storage cold tier
   - Backup snapshot durumu (Restic)
   - Auto-refresh 30s

/admin/rag  →  LLM/RAG pipeline gözlem
   - Sağlık (feature flags, counts)
   - Karşılaştırma (eval benchmark)
   - Atıf (citation accuracy)
   - Yeniden Sıralama (rerank latency stats)
   - RAPTOR (cluster build)
   - İnceleyici (manuel query inspect)
   - Performans (#440 — pipeline metric comparison)
```

### Yeni metric/dashboard ekleneceğinde karar matrisi

| İçerik | Yer |
|---|---|
| VPS / network / disk / RAM / CPU | `/admin/observability` |
| Database (Postgres) sağlık veya boyut | `/admin/observability` |
| Storage (MinIO, S3, cold tier) | `/admin/observability` |
| Backup / restore / snapshot | `/admin/observability` |
| **LLM token / latency / cost** | **`/admin/rag` (yeni sekme)** |
| **Embedding veya rerank stats** | **`/admin/rag` (mevcut sekmeler)** |
| **Citation / halü oranı** | **`/admin/rag` (mevcut "Atıf" veya yeni)** |
| **Prompt eval skorları** | **`/admin/rag` (mevcut "Karşılaştırma")** |
| **RAPTOR / cluster build** | **`/admin/rag` (mevcut "RAPTOR")** |
| Auth / KVKK / takedown istatistikleri | `/admin/legal` (ayrı, MVP-1) |
| User / quota / billing | `/admin/users` (ayrı) |

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| **Her metric için yeni sayfa** (örn. `/admin/pipeline-perf`, `/admin/citations`) | İzole sayfalar | Sidebar şişer, navigasyon dağınık | Reddedildi |
| **Tek bir mega `/admin/dashboard` sayfası** (her şey burada) | Tek tıkta tüm gözlem | Sayfa devasa, lazy-loading karışık, ayrı concerns karışır | Reddedildi |
| `/admin/observability`'a pipeline da ekle | Tek "gözlem" sayfası | Infra ile pipeline farklı concerns; bakım yükü artar | Reddedildi |
| **`/admin/observability` infra, `/admin/rag` pipeline (mevcut yapı)** | Concerns ayrı, sekme bazlı genişletme kolay | Yeni geliştirici "iki sayfa neden var" sorabilir → bu decision sayfası | **Seçildi** |
| Yeni `/admin/pipeline` üst sayfası (rag + cost + eval birleştir) | RAG'i daha jenerik bir başlık altında topla | Mevcut `/admin/rag` linkleri kırılır, refactor maliyeti yüksek, "pipeline" çok genel terim | Reddedildi (MVP-2.1 sonrası) |

## Sonuçlar

- **Etkilenen sayfalar:**
  - [`apps/web/src/app/admin/observability/page.tsx`](../../apps/web/src/app/admin/observability/page.tsx) — sadece infra
  - [`apps/web/src/app/admin/rag/page.tsx`](../../apps/web/src/app/admin/rag/page.tsx) — LLM/RAG, 7 sekme (#440 ile Performans eklendi)
- **Etkilenen mimari:** Yeni LLM/pipeline observability özellikleri için ayrı `/admin/...` route açılmaz, /admin/rag'a sekme eklenir.
- **Etkilenen dokümanlar:**
  - [INDEX.md §4](../../INDEX.md) — locked decision listesi
  - Wiki [[pipeline-performance-baseline]] (UI yolu yansıtıldı)
- **Etkilenen kararlar:** [[endpoint-naming-policy]] (eylem-bazlı endpoint adlandırma) ile birlikte alınır — `/admin/rag/pipeline-comparison` hem doğru yere hem doğru ismeyle eklendi.

## Geri alma maliyeti

Orta. Mevcut sekmeler `/admin/rag` URL'sinde, kullanıcı linkleri ve bookmark'lar olabilir. Eğer `/admin/pipeline` üst sayfası açılmak istenirse:
1. `/admin/rag/*` → `/admin/pipeline/rag/*` redirect ekle (Next.js redirects config)
2. Bookmarks 30 gün içinde otomatik resolve olur
3. Wiki + INDEX dokümanları güncellenir

Şu an yapma sebebi yok — MVP-2.1 sonrası bir gözden geçirme iyi olur (özellikle MVP-3 cost dashboard eklenirken).

## Uygulama (mevcut)

PR [#441](https://github.com/selmanays/nodrat/pull/441) ile:

```diff
// apps/web/src/app/admin/rag/page.tsx
type TabKey =
  | "health"
  | "benchmark"
  | "citation"
  | "rerank"
  | "raptor"
  | "inspector"
+ | "performance";

const TABS = [
  ...
+ { key: "performance", label: "Performans" },
];
```

Browser yolu: https://nodrat.com/admin/rag → "Performans" sekmesi.

## İlişkiler

- **Bağlı varlıklar:** —
- **Bağlı kavramlar:** [[provider-abstraction]] (LLM çağrıları gözlemlenebilir)
- **Bağlı kararlar:** [[endpoint-naming-policy]] (eş zamanlı alındı)
- **Bağlı topics:** [[pipeline-performance-baseline]] (Performans sekmesi bu sayfanın UI yansıması)

## Kaynaklar

- [GitHub Issue #440](https://github.com/selmanays/nodrat/issues/440) — UI gerekçesi
- [GitHub PR #441](https://github.com/selmanays/nodrat/pull/441) — uygulama
- [apps/web/src/app/admin/observability/page.tsx](../../apps/web/src/app/admin/observability/page.tsx) — infra page
- [apps/web/src/app/admin/rag/page.tsx](../../apps/web/src/app/admin/rag/page.tsx) — RAG page (Performans sekmesi)
- [INDEX.md §4 (Çekirdek kararlar — locked)](../../INDEX.md)
