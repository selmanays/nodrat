# `modules/clusters/`

**Layer:** middle — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** **active** (Phase 2 — sixth module migrated, scope-limited).

Article-level **event clustering** domain modülü. Article (haber) maddelerinin
zaman + embedding bazlı kümelenmesi. Eş zamanlı olay / aynı konu makaleleri
`event_cluster` + `event_article` ilişkilerinde toplanır.

## Scope sınırı (kritik)

Bu modül **YALNIZ article-level event clustering** kapsar. Aşağıdakiler
bu modüle dahil **DEĞİLDİR**:

| Yer almaz | Nedeni | Ne zaman taşınacak | Nereye taşınacak |
|---|---|---|---|
| **RAPTOR clustering** (`workers/tasks/raptor.py`) | RAG hiyerarşik kümeleme — domain rag | Phase 5 | `modules/rag/tasks/raptor.py` |
| **Pivot user research clustering** ([`core/research_clustering.py`](../../core/research_clustering.py) + [`workers/tasks/cluster_assigner.py`](../../workers/tasks/cluster_assigner.py); #1015) | User research kümeleme — domain generations | Phase 6 | `modules/generations/research_clustering/` |
| **`api/admin_clusters.py`** | `ResearchCluster` + `MessageCluster` gözlemi (research domain, article-event DEĞİL) | Phase 6 | `modules/generations/admin/research_clusters.py` (veya benzeri) |
| **`research_cluster` model** ([`app/models/research_cluster.py`](../../models/research_cluster.py)) | Generations domain'ine ait (Pivot #1015) | Phase N+1 | model ownership generations (master plan §2.4 revize); fiziksel taşıma flat-rules sonrasında |

## Layout (Phase 2 PR 6 sonrası — sadece article-event)

- `__init__.py` — minimal facade (yalnız article-event clustering; admin yüzeyi yok)
- `clustering.py` — article event clustering core logic (embedding similarity, time window, cluster lifecycle)
- `tasks/clustering.py` — Celery task `tasks.clustering.*` (`refresh_clusters` hourly Beat + `cluster_article` lazy-from-embedding)

**Bu modülde admin/ yok.** Mevcut `/admin/clusters` URL'i legacy `app/api/admin_clusters.py` üzerinden servis ediliyor (research_cluster gözlemi). Phase 6'da generations taşıması sırasında bu route doğru sahibine kaydırılacak.

## Public API

| Symbol | Type | Note |
|---|---|---|
| `cluster_article` | Celery task | Called lazily from `workers/tasks/embedding.py` after chunk embed; chains to `generate_agenda_card` |
| `refresh_clusters` | Celery Beat task | Hourly: refresh status + importance + freshness across active clusters |

## References

- Architecture: [`docs/engineering/modular-monolith-architecture.md`](../../../../docs/engineering/modular-monolith-architecture.md) §3.2
- Boundary: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)

## Migration history

- 2026-05-20: Phase 2 PR 6 — migrated **2 files** (`app.core.clustering`,
  `app.workers.tasks.clustering`). `api/admin_clusters.py` **intentionally
  excluded** (research-domain admin route — deferred to Phase 6 generations).
  Behavior-preserving; broader-grep clean.
- 2026-05-20: Phase 1 PR — scaffold created.
