---
type: decision
title: Admin Route Domain Ownership (ops/ Stays Narrow)
slug: admin-route-domain-ownership
status: locked
decided_on: 2026-05-20
decided_by: founder
created: 2026-05-20
updated: 2026-05-20
sources:
  - wiki/decisions/modular-monolith-boundary.md
  - wiki/plans/modular-monolith-transition-master-plan.md§5
tags:
  - architecture
  - modular-monolith
  - admin
  - ops
  - locked-decision
aliases:
  - admin-ownership
  - ops-narrow
---

# Admin Route Domain Ownership (ops/ Stays Narrow)

> **Karar:** Domain-spesifik admin route'ları ilgili modülün `<module>/admin/` alt klasöründe yaşar. Merkezi `modules/ops/` modülü **yalnız cross-cutting operasyonel araçları** içerir: dashboard, audit, queue, system, maintenance. URL prefix `/admin/*` korunur (harici sözleşme).
>
> **Durum:** locked
> **Tarih:** 2026-05-20

## Bağlam

Mevcut `apps/api/app/api/` 14 admin route var (admin_sources, admin_articles, admin_rag, admin_billing, admin_users, admin_dashboard, admin_audit, admin_queue, admin_system, admin_settings, admin_prompts, admin_sft, admin_media, admin_clusters). Hepsi tek klasörde — domain ayrımı sadece dosya adı prefix'i (`admin_*.py`).

Bu yapı "merkezi admin god-modül" doğurma riski taşır: tek bir `admin/` paketi her şeyi import eder, modül sınırı yok olur, "RAG dashboard değişikliği" diye PR'lar admin paketinin tamamına yayılır.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Tek merkezi `modules/admin/` modülü | "Admin yüzeyi tek yer" basit görünüyor | God-modül doğar; domain boundary çöker; admin tek PR'da büyür | **Reddedildi** |
| Hiç admin ayrımı yapma, route'lar modülün `routes.py`'sinde karışsın | İskelet çok ince | App ve admin authz/UX farklı; tek dosya karmaşık | **Reddedildi** |
| **Domain admin'ler modülde, cross-cutting ops dar bir `ops/`'da** | Her modül kendi admin'ini taşır; ops yalnızca generik operasyonel | Daha çok dosya | **Seçildi** |

## Konum kuralı

| Tür | Konum | URL |
|---|---|---|
| **Domain-spesifik admin** | `modules/<mod>/admin/routes.py` + `modules/<mod>/admin/service.py` | `/admin/<sub>/...` |
| **Cross-cutting operasyonel** | `modules/ops/{dashboard,audit,queue,system,maintenance}/` | `/admin/<sub>/...` |

URL prefix `/admin/*` **değişmez** — harici sözleşme. Kod path'i `modules/ops/`, URL `/admin/dashboard`, `/admin/audit` vb.

## Domain admin mapping

| Eski route | Yeni konum |
|---|---|
| `api/admin_sources.py` | `modules/sources/admin/routes.py` |
| `api/admin_articles.py` | `modules/articles/admin/routes.py` |
| `api/admin_rag.py` | `modules/rag/admin/routes.py` |
| `api/admin_clusters.py` | `modules/clusters/admin/routes.py` |
| `api/admin_media.py` | `modules/media/admin/routes.py` |
| `api/admin_sft.py` | `modules/sft/admin/routes.py` |
| `api/admin_prompts.py` | `modules/prompts_admin/routes.py` |
| `api/admin_settings.py` | `modules/settings_admin/routes.py` |
| `api/admin_billing.py` | `modules/billing/admin/routes.py` |
| `api/admin_users.py` | `modules/accounts/admin/routes.py` |

## ops/ kapsamı

`modules/ops/` yalnız şunları içerir:

| Alt-paket | Eski karşılığı |
|---|---|
| `ops/dashboard/` | `api/admin_dashboard.py` (toplu metrics) |
| `ops/audit/` | `api/admin_audit.py` (event log + admin_audit_log) |
| `ops/queue/` | `api/admin_queue.py` + `workers/tasks/maintenance.py` (Celery queue browser, DLQ, manuel replay) |
| `ops/system/` | `api/admin_system.py` (disk + CPU + RAM telemetry) |
| `ops/maintenance/` | maintenance tasks (body_html_drop, cold_tier_archive) |

`ops/`'un model sahipliği:
- `models/event.py` — flat (gelecek ops/observability adayı)
- `models/job.py` — flat (gelecek ops/queue sahibi)
- `models/provider_log.py` — flat (sahibi `shared/observability/`; ops yalnız görüntüler)

## ops/'un özel import kuralı

`ops/` modüllerin **public service.py / repository.py** yüzeylerini okuyabilir (dashboard aggregation için). Diğer modüller `ops/`'a import yapamaz (yukarı yön yasak).

```
ops/dashboard/service.py:
    from modules.sources.service import sources_service       # OK (public API)
    from modules.articles.service import articles_service     # OK
    from modules.rag.service import rag_service               # OK
    from modules.sources.internal.fetcher import fetch        # YASAK (internal)
```

## Sonuçlar

- Domain admin değişikliği → ilgili modülün PR'ı (RAG dashboard tweak = rag modülü PR'ı).
- Cross-cutting ops değişikliği → ops modülünün PR'ı.
- URL backward-compat korunur.

## Geri alma maliyeti

Bu kural gevşetilip tek merkezi `admin/`'a dönülürse: god-modül oluşur, domain boundary çöker, paralel PR'lar admin paketinde çakışır. Geri alma için tüm admin route'lar tekrar modüllere dağıtılır. **Orta maliyet.**

## İlişkiler

- **Bağlı kararlar:** [[modular-monolith-boundary]], [[import-direction-rules]]

## Kaynaklar

- [wiki/plans/modular-monolith-transition-master-plan.md §5](../plans/modular-monolith-transition-master-plan.md)
- [docs/engineering/modular-monolith-architecture.md](../../docs/engineering/modular-monolith-architecture.md)
