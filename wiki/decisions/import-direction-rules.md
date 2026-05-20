---
type: decision
title: "Import Direction Rules (Boundary Enforcement)"
slug: "import-direction-rules"
status: locked
decided_on: 2026-05-20
decided_by: founder
created: 2026-05-20
updated: 2026-05-20
sources:
  - "wiki/decisions/modular-monolith-boundary.md"
  - "wiki/plans/modular-monolith-transition-master-plan.md§3"
tags: ["architecture", "modular-monolith", "import-linter", "locked-decision"]
aliases: ["import-rules", "boundary-rules"]
---

# Import Direction Rules (Boundary Enforcement)

> **Karar:** Modüller arası import yönü katman-bazlı kuraldan geçer. `import-linter` ile CI'da fail edilir. Faz 1'de `modules/*` ve `shared/*` baştan **strict**; legacy `app.core.*` + `app.api.*` **report-only**. Her modül taşındıkça strict kapsamına alınır; Faz 8'de genel strict.
>
> **Durum:** locked
> **Tarih:** 2026-05-20

## Bağlam

Domain-based modular monolith ([[modular-monolith-boundary]]) sınırlarını **statik araçla** zorlamadan kalıcılık sağlanmaz. Tek geliştirici + LLM workflow + paralel worktree ortamında "elde tut" disiplini hata kaldırmaz; CI gate şart.

## Allowed imports

| From | Allowed to |
|---|---|
| `generations` | `rag`, `articles`, `sources`, `accounts`, `billing`, `style_profiles`, `entities`, `shared/*` |
| `rag` | `articles`, `sources`, `entities`, `shared/*` |
| `crawler` | `articles`, `sources`, `shared/*` |
| `clusters` | `articles`, `shared/*` |
| `entities` | `articles`, `shared/*`, `shared/prompts/ner` |
| `media` | `articles`, `shared/storage`, `shared/providers/nim_vlm`, `shared/*` |
| `style_profiles` | `accounts`, `shared/*` |
| `sft` | `generations`, `articles`, `accounts`, `shared/*` |
| `articles` | `sources`, `shared/*` |
| `sources` | `shared/*` |
| `accounts` | `shared/*` |
| `billing` | `accounts`, `shared/providers/lemonsqueezy`, `shared/observability/cost_tracker` (read-only), `shared/*` |
| `legal` | `accounts`, `shared/*` |
| `prompts_admin` | `shared/runtime_config`, `shared/prompts` (read-only), `shared/*` |
| `settings_admin` | `shared/runtime_config`, `shared/*` |
| `ops` | Her modülün public `service.py` / `repository.py` + `shared/*` |
| `public` | `rag.facade`, `shared/*` |

## Forbidden imports (CI fail)

| From | Forbidden to | Neden? |
|---|---|---|
| `rag` | `crawler`, `generations` | RAG, çekme detayını veya orkestrasyonu bilmez |
| `crawler` | `rag`, `generations` | Aşağıdan yukarı |
| `articles` | `rag`, `generations`, `crawler`, `clusters` | Kernel yukarı bakmaz |
| `sources` | `articles`, `crawler`, `rag`, `generations` | Kernel'in kerneli |
| `accounts` | `billing`, `generations`, `rag`, `articles`, `sources` | Bağımsız identity |
| `clusters` | `rag`, `generations` | Üst seviyeye okumaz |
| `entities` | `rag`, `generations` | Üst seviyeye okumaz |
| `media` | `rag`, `generations` | Üst seviyeye okumaz |
| `style_profiles` | `generations`, `rag` | Üst seviyeye okumaz |
| `sft` | `crawler` | Crawler iç detayını bilmez (articles üzerinden geçer) |
| Tüm modüller | `<other_module>/internal/*` | Yalnız public API |
| Tüm modüller | `ops` | Ops yukarı bakar; modüller ops'u import etmez |
| `shared/*` | `modules/*` | Shared yukarı bakmaz |

## Özel durumlar

- **Auth dependency**: Tüm route'lar `accounts.deps.get_current_user`'ı import eder. **Shared dependency** kabulü; ihlal değil.
- **Pydantic schemas**: Modüller arası DTO geçişi `<mod>/schemas.py`. Cross-module schema import = OK (read-only veri sözleşmesi).
- **Workers**: `shared/workers/celery_app.py` task autodiscover ile `modules/<mod>/tasks/*` toplar. Task fonksiyonları kendi modüllerinin service'ini import eder (modül içi, "yukarı yön" değil).
- **Models flat (Faz N+1'e kadar)**: Tüm modüller `from app.models.<entity> import X` kullanır. Bu özel istisna — boundary kuralı modeller dışında uygulanır.

## Strict kapsam takvimi

| Faz | Strict kapsamı | Report-only kapsamı |
|---|---|---|
| 1 | `modules/*`, `shared/*` | `app.core.*`, `app.api.*` |
| 2-7 | Yukarıdaki + her taşınan modül | Kalan legacy |
| 8 | Genel (legacy boş) | — |

## Implementation

- **Tool:** `import-linter` (Python).
- **Config konumu:** `apps/api/pyproject.toml` `[tool.importlinter]` (varsayılan tercih) veya `.importlinter.cfg` (Faz 1 PR'ında karar).
- **CI step:** `.github/workflows/ci.yml` içine `lint-imports` job'u eklenir; her PR'da çalışır.
- **Yerel:** Developer `lint-imports` komutunu pre-commit hook'una bağlayabilir.

## Sonuçlar

- İhlal CI'da kırmızı; PR merge edilemez.
- Yeni modül eklenince allowed/forbidden tablosu bu sayfada güncellenir + ilgili PR docs sync taşır.
- Karar değişimi: yeni decision + bu sayfa superseded.

## Geri alma maliyeti

Bu kural gevşetilirse: god-modül oluşumu kontrolsüz; sources/articles'ın kerneli kaybolur; refactor yarı yolda durur. Geri alma için tüm modüllerde import graph'ını manuel temizlemek gerek. **Yüksek maliyet.**

## İlişkiler

- **Bağlı kararlar:** [[modular-monolith-boundary]]
- **Bağlı playbook:** [[refactor-pr-checklist]], [[new-feature-module-checklist]]

## Kaynaklar

- [docs/engineering/modular-monolith-architecture.md](../../docs/engineering/modular-monolith-architecture.md) §Import Boundaries
- [wiki/plans/modular-monolith-transition-master-plan.md §3](../plans/modular-monolith-transition-master-plan.md)
