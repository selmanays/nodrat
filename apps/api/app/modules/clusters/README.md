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

## Layout (Phase 2 PR 6 + T8-8 sonrası)

- `__init__.py` — lazy facade (yalnız docstring + `__all__: list[str] = []`; T8-PRE-1 disciplinine doğal uyum)
- `clustering.py` — article event clustering core logic (embedding similarity, time window, cluster lifecycle)
- `models.py` — `EventCluster` + `EventArticle` ORM (T8-8'de eklendi; önceden `app/models/event.py`)
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

- 2026-05-28: **T8-8** — `EventCluster` + `EventArticle` ORM modelleri
  `app/models/event.py`'den `models.py`'e taşındı (100% rename + facade re-export).
  1 production caller flip (`modules/generations/tasks/agenda.py:32` — eager,
  `app.modules.clusters.models import EventCluster`). Wave C ısınma (T8 risk-classified
  mode altında ilk safe candidate; v78 Option B FAIL sonrası core-consumer-free
  modeli kuralı uygulandı). Behavior-preserving; veri güvenliği invariant korunur
  (`event_clusters`/`event_articles` tablolarına dokunulmadı; raw SQL caller'lar
  `core/data_sufficiency`, `core/retrieval`, `api/admin_rag` — tablo adı sabit,
  etkilenmedi).
- 2026-05-20: Phase 2 PR 6 — migrated **2 files** (`app.core.clustering`,
  `app.workers.tasks.clustering`). `api/admin_clusters.py` **intentionally
  excluded** (research-domain admin route — deferred to Phase 6 generations).
  Behavior-preserving; broader-grep clean.
- 2026-05-20: Phase 1 PR — scaffold created.
