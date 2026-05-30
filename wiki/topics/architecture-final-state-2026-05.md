---
type: topic
title: "Architecture Final State — Modular Monolith (2026-05)"
slug: architecture-final-state-2026-05
status: live
created: 2026-05-30
updated: 2026-05-30
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md"
  - "wiki/decisions/god-file-facade-first.md"
  - "wiki/decisions/modular-monolith-boundary.md"
  - "wiki/topics/modular-monolith-v3-deep-split-mini-plan.md"
tags:
  - modular-monolith
  - architecture
  - final-state
  - invariants
aliases:
  - architecture-final-state
  - mm-final-state
---

# Architecture Final State — Modular Monolith (2026-05)

> **TL;DR:** Üç ardışık modular-monolith milestone'u (#18 v1 + #19 v2 + #20 v3) **KAPANDI**. Repo katmanlı bir modular monolith: **21 domain modülü** (`app/modules/*`) + **12 shared kernel** (`app/shared/*`) + **7 cross-domain aggregator** (`app/api/*`) + `app/core/*` (retrieval çekirdeği — 10 `_retrieval_*` submodül + facade). **16 import-linter contract** CI-gate'li (0 broken). En büyük god-file (`retrieval.py` 1926→97 saf facade) deep-split tamamlandı. Tek açık future-hardening işi: orchestrator `_research_stream_body` deep-split → backlog [#1421](https://github.com/selmanays/nodrat/issues/1421). Production stabil + healthy; tüm refactor **behavior-preserving** (no schema/migration/data/embedding mutation).

## 1. Kapanan milestone'lar

| Milestone | Kapsam | Durum |
|---|---|---|
| **#18 Modular Monolith v1** | Mimari iskelet + boundary full-strict + low-risk modüller + domain services + god-file characterization safety-net | ✅ closed (47) |
| **#19 Modular Monolith v2** | Route/primitive relocation (app/api 20→7) + facades + accounts domain + crawler/observability→shared | ✅ closed (2) |
| **#20 Modular Monolith v3** | God-file deep internal splits: T5 char + P5 retrieval 9-step + P6 facade | ✅ closed (11) |

**İlişkili (kapalı):** T6 #1085 (god-file facade strategy) · T7 #1086 (core consumer cleanup) · T8 #1087 (model relocation) · P7a #1095 (frontend api.ts split) · Phase 7b #1096 · Phase 8 #1097 (boundary hardening) · N+1 #1098.

### #20 reconciliation detayı (Option A, 2026-05-30)
- **T5 #1084** ✅ — char done (retrieval golden 52 + SSE replay 10/10 + citation 30 + tool_choice #1411 + #904 status); 2 deferred-belgeli (eval CI-gate corpus-imkansız + extraction-snapshot P4-kapsamı).
- **P5 #1093** ✅ — `core/retrieval.py` **1926→97 saf facade**; 8 pure-move PR (#1412-#1419); **10 `_retrieval_*` submodül**; prod-verified.
- **P6 #1094** ✅ closed-with-documented-deferred — facade + SSE replay + tüm pure-helper extraction DONE; orchestrator deep-split → future [#1421] (sahte-kapanış YOK).

## 2. Mimari yapı (mevcut)

```
apps/api/app/
├── core/          retrieval çekirdeği — retrieval.py (97-satır facade) + 10 _retrieval_* submodül
│                  (ner/fetch/parent/settings/affinity/agenda/chunks/phrase/scoring/vector)
│                  + db, config, research_tools, cleaning, content_quality
├── modules/       21 domain (kernel + middle + business):
│                  accounts, agenda, articles, billing, clusters, conversations,
│                  crawler, embedding, entities, generations, legal, media, ops,
│                  prompts_admin, public, rag, settings_admin, sft, sources, style_profiles
├── shared/        12 kernel-seviye (Seviye 0): crawl, db, email, extraction, http,
│                  observability, prompts, providers, runtime_config, storage, util, workers
└── api/           7 cross-domain aggregator (BFF/orchestration — meşru):
                   app_me, app_research, app_research_stream, _research_stream_context,
                   admin_clusters, admin_rag, __init__
```

- **`app/api/` aggregator'ları kasıtlı api/'de kalır:** birden fazla domain'i import ettikleri için (accounts→business + rag→generations yasakları nedeniyle) modüle taşınamaz; BFF/orchestration katmanı.
- **`core/retrieval.py` = saf facade:** module-level fonksiyon yok; tüm semboller `_retrieval_*` submodüllerinden re-export (`# noqa: F401`). Caller'lar `from app.core.retrieval import X` ile değişmeden çalışır.

## 3. Korunan invariants

### Boundary (import-linter — 16 contract, CI hard-gate, 0 broken)
- `core` → `modules` **forbidden** (kernel domain'lere bağımlı olamaz)
- `rag` → `crawler` / `generations` **forbidden**
- `sources` → diğer-domain **forbidden** (yalnız accounts auth cross-cutting + articles kernel istisna)
- `accounts` → `business` **forbidden**
- `domain` → `ops` **forbidden** (FailedJob/AdminAuditLog documented exception)
- `shared` → {`modules`, `core`, `api`, `models`} **forbidden** (Seviye 0 leaf)
- **CI otoriter:** local lint-imports cache yanıltabilir → CI sonucu kaynak (P5b dersi).

### Veri güvenliği
- **No schema / migration / data / embedding mutation** — tüm modular-monolith refactor'ları behavior-preserving.
- Embedding/chunk/RAG-index/vector kayıtları silinmez/truncate edilmez/toplu-reprocess edilmez ([[feedback_embedding_rag_index_safety]]).
- Tüm v1/v2/v3 PR'ları: schema/migration/data dokunmadı; ORM relocation'ları git-mv (tablo/kolon/index AYNEN).

### Behavior-preserving refactor
- God-file split = pure-move (logic dokunulmaz) → recall/ranking by-construction sabit.
- Pure-logic değişiklikler CI char-test'le korunur; corpus-bağımlı recall manuel/staging gate (CI-able değil).

## 4. Production durumu

- **Deploy:** merge → CI → `deploy.yml` workflow_run otomatik VPS deploy (Contabo VPS 40, `/opt/nodrat`, image-based). Kod-PR → FULL deploy; docs/wiki-only → SKIP (#1114 two-job gating).
- **Son doğrulama (2026-05-30):** retrieval saf facade canlı (module-fns=[] + 10 submodül + re-export 14/14); container'lar `Up healthy`; `/health` 200. **Regression YOK.**
- **Deploy uyarısı:** code-PR deploy "cancelled/failure" çoğu kez `/health` smoke false-fail (cold-start) VEYA swap-fail (B2 exit-255) → SSH ile doğrula, re-run gerekirse ([[feedback_deploy_smoke_false_fail]]).

## 5. Feature development kuralları (bundan sonra geçerli)

1. **Yeni domain kodu → `app/modules/<domain>/`** (kernel/middle/business seviyesine uy). Boundary'ye dikkat: `core`→`modules` yasak, `shared` leaf, domain→domain yalnız izinli yönlerde.
2. **Cross-domain orchestration (birden fazla domain) → `app/api/`** aggregator (BFF). Zorla modüle taşıma.
3. **Pure HTML/content/parsing primitive → `app/shared/extraction`** (Seviye 0); I/O-suz kütüphane.
4. **Her PR öncesi pre-flight:** `ruff check` + `ruff format --check` TÜM değişen `.py` ([[feedback_ruff_preflight_all_files]]) + `lint-imports` (16/16) + targeted + full unit suite. **CI otoriter.**
5. **Relocation/rename'de 5-form gizli-caller taraması:** symbol-import + module-import (`from app.X import Y`) + patch()-string-target + ast/read_text source-inspection. Re-export'ta `# noqa: F401` koru (ruff `--fix` unused sanıp kaldırır → dış caller kırılır).
6. **Veri/schema/migration/embedding mutasyonu → DURDUR + mini plan + açık onay.** Doğal idempotent backfill normal.
7. **`docs/` LLM tarafından yazılmaz** (açık yetki istisnası hariç); **`wiki/` yazımı yalnız main/wiki-branch'inde**; mimari karar = ayrı decision sayfası + bidirectional backlink + log/index sync.
8. **Deploy doğrulama:** merge sonrası main CI (8/8) + deploy/smoke; "cancelled/failure" → SSH ile functional success doğrula, körlemesine re-deploy yok.

## 6. Açık / future (backlog)

- **[#1421](https://github.com/selmanays/nodrat/issues/1421) (enhancement, backlog, milestone'suz)** — "P6.1 Full tool-loop TestClient gate + `_research_stream_body` orchestrator split". Ön-koşul: full tool-loop TestClient integration gate. Modular-monolith hedefini bloklamaz; future-optional hardening.
- Diğer açık ürün milestone'ları (modular-monolith dışı): #16 RAG Quality, #17 Pivot, #3 MVP-3, #5 Faz 5, #6 Backlog Legal.

## İlişkiler
- **Master plan:** [[modular-monolith-transition-master-plan]] (§13 status board + §586/§588).
- **v3 detay:** [[modular-monolith-v3-deep-split-mini-plan]] (P5 split + P6 deferred).
- **Locked kararlar:** [[god-file-facade-first]], [[modular-monolith-boundary]], [[import-direction-rules]].
- **Disiplin:** [[refactor-pr-checklist]], [[feedback_ruff_preflight_all_files]], [[feedback_embedding_rag_index_safety]], [[feedback_deploy_smoke_false_fail]].

## Kaynaklar
- [wiki/plans/modular-monolith-transition-master-plan.md](../plans/modular-monolith-transition-master-plan.md)
- [wiki/decisions/god-file-facade-first.md](../decisions/god-file-facade-first.md)
- GitHub milestones: [#18](https://github.com/selmanays/nodrat/milestone/18) · [#19](https://github.com/selmanays/nodrat/milestone/19) · [#20](https://github.com/selmanays/nodrat/milestone/20)
