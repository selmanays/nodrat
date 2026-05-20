---
type: decision
title: "Modular Monolith Boundary (Domain-Based Layering)"
slug: "modular-monolith-boundary"
status: locked
decided_on: 2026-05-20
decided_by: founder
created: 2026-05-20
updated: 2026-05-20
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md§1"
  - "docs/engineering/modular-monolith-architecture.md"
tags: ["architecture", "modular-monolith", "locked-decision"]
aliases: ["mm-boundary"]
---

# Modular Monolith Boundary (Domain-Based Layering)

> **Karar:** Nodrat domain-bazlı modüler monolite dönüşür. Microservice'e gidilmez. `apps/api/app/modules/<domain>/` + `apps/api/app/shared/<infra>/` ağacı; 4 mantıksal katman (kernel → orta → üst, paralel + cross-cutting).
>
> **Durum:** locked
> **Tarih:** 2026-05-20

## Bağlam

Mevcut `apps/api/app/` yatay kesim (api/core/models/workers/providers) — domain sınırı yok. `core/` 47 dosya tek düz klasör; `app.api.*` route'ları iş mantığı + LLM tool çağrılarını içeriyor. God-file'lar (retrieval.py 2174, app_research_stream.py 1440, extractor.py 1189) sessiz regresyon riski yaratıyor. Sources/articles/generations/rag/crawler gibi domain'ler net sınır olmadan birbirini import ediyor.

Hedef: tek repo + tek deploy, ama **domain-bazlı dikey kesim**.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Microservice'e geç | Sınır en sıkı | Tek dev + LLM workflow için aşırı maliyet; deploy karmaşası; FK ilişkileri RPC'ye dönüşür | **Reddedildi** |
| Mevcut layer-bazlı yapıda kal | Refactor sıfır | `core/` çöplüğü büyür; god-file'lar sessiz regresyon yaratmaya devam eder; boundary yok | **Reddedildi** |
| Sources/articles'ı crawler altına koy | "Yazan modül sahibi" mantıklı | Article çok yerden okunur (rag, generations, clusters, sft) — hepsi crawler'ı import etmek zorunda kalır → boundary saçma | **Reddedildi** |
| Toptan refactor (12 gün donmuş trunk) | Tek atomik geçiş | MVP-1.8 RAG + RC3-B akışını engeller; sessiz regresyon riski; geçmiş CI körlüğü dersi | **Reddedildi** |
| **Domain-based modular monolith, boundary-first evrimsel** | Tek deploy korunur; sınır net; refactor MVP temposunu engellemez; god-file disiplini facade ile | Refactor 2-3 ay'a yayılır | **Seçildi** |

## Katman seviyeleri

```
Seviye 4 (üst):      generations
Seviye 3 (orta):     crawler, rag, clusters, entities, media, style_profiles, sft
Seviye 2 (kernel):   sources, articles                     ← domain kernel (DDD shared kernel)
Seviye 1 (paralel):  accounts, billing, legal, prompts_admin, settings_admin
Seviye 0 (alt):      shared/* (db, providers, prompts, util, http, storage,
                                email, observability, runtime_config, workers)
Cross-cutting:       ops    — modüllerin public API'larını okur (TEK İSTİSNA)
Cross-cutting:       public — yalnız rag.facade + health
```

## Modüller (18 + shared)

Tam liste + sorumluluk: `wiki/plans/modular-monolith-transition-master-plan.md §2.2`.

Özel sahiplikler (kullanıcı kararı 2026-05-20):
- `takedown` — legal sahip; model `app/models/takedown.py` flat.
- `cost_tracker` — `shared/observability/`; billing read-only.
- `conversation_context` — `modules/generations/conversation/context.py`; shared değil.
- `settings_store`, `prompts_store` — `shared/runtime_config/`; admin modülleri yalnız CRUD yüzeyi.
- `event.py`, `job.py`, `provider_log.py` — şimdilik flat; sahipleri: ileride observability/ops adayları.

## Sonuçlar

- Etkilenen kavramlar: [[import-direction-rules]], [[models-flat-until-conditions]], [[god-file-facade-first]], [[admin-route-domain-ownership]].
- 8 fazlı geçiş planı: `wiki/plans/modular-monolith-transition-master-plan.md §9`.
- Karar değişimi: yeni decision sayfası + bu sayfa `superseded by` ile bağlanır.

## Geri alma maliyeti

Bu karar değiştirilirse: master plan tamamen yeniden yazılır, 8 fazlı geçiş hattı tekrar planlanır, açılmış GitHub issue'ları kapatılır/yeniden organize edilir, `wiki/decisions/*` ilgili 5 sayfa superseded işaretlenir. **Yüksek maliyet.** Bu yüzden locked.

## İlişkiler

- **Bağlı kararlar:** [[import-direction-rules]], [[models-flat-until-conditions]], [[god-file-facade-first]], [[admin-route-domain-ownership]], [[no-internal-backcompat-aliases]]
- **Bağlı playbook:** [[refactor-anti-patterns-do-not-do]], [[refactor-pr-checklist]], [[new-feature-module-checklist]]
- **Master plan:** `wiki/plans/modular-monolith-transition-master-plan.md`

## Kaynaklar

- [docs/engineering/modular-monolith-architecture.md](../../docs/engineering/modular-monolith-architecture.md)
- [docs/engineering/refactor-playbook.md](../../docs/engineering/refactor-playbook.md)
- [wiki/plans/modular-monolith-transition-master-plan.md](../plans/modular-monolith-transition-master-plan.md)
