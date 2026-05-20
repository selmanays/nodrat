# `modules/clusters/`

**Layer:** middle — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** **active** (Phase 2 — sixth module migrated).

Article-level **event clustering** domain modülü. Article (haber) maddelerinin
zaman + embedding bazlı kümelenmesi. Eş zamanlı olay / aynı konu makaleleri
`event_cluster` + `event_article` ilişkilerinde toplanır.

## Scope sınırı (önemli)

Bu modül **YALNIZ article-level event clustering** kapsar. Aşağıdakiler
bu modüle dahil **DEĞİLDİR**:

| Yer almaz | Ne zaman taşınacak | Nereye taşınacak |
|---|---|---|
| **RAPTOR clustering** (`workers/tasks/raptor.py`) | Phase 5 | `modules/rag/tasks/raptor.py` |
| **Pivot user research clustering** ([`core/research_clustering.py`](../../core/research_clustering.py) + [`workers/tasks/cluster_assigner.py`](../../workers/tasks/cluster_assigner.py); #1015) | Phase 6 | `modules/generations/research_clustering/` |
| **`research_cluster` model** ([`app/models/research_cluster.py`](../../models/research_cluster.py)) | Phase N+1 | model ownership generations (master plan §2.4 revize) |

## Layout

- `__init__.py` — public facade (`admin_router` re-export)
- `clustering.py` — article event clustering core logic (embedding similarity, time window, cluster lifecycle)
- `tasks/clustering.py` — Celery task `tasks.clustering.*` (`refresh_clusters` hourly Beat)
- `admin/routes.py` — admin FastAPI router (URL: `/admin/clusters/*`)

## References

- Architecture: [`docs/engineering/modular-monolith-architecture.md`](../../../../docs/engineering/modular-monolith-architecture.md) §3.2
- Boundary: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)

## Migration history

- 2026-05-20: Phase 2 PR 6 — migrated **3 files** from legacy paths
  (`app.core.clustering`, `app.workers.tasks.clustering`, `app.api.admin_clusters`).
  Behavior-preserving. **research_clustering + cluster_assigner explicitly
  NOT included** (belong to generations Phase 6).
- 2026-05-20: Phase 1 PR — scaffold created.
