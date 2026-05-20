"""Module: clusters

Domain: article-level event clustering. Haber maddelerinin (articles) zaman +
embedding bazlı kümelenmesi (event_cluster + event_article ilişkileri).

**Scope sınırı (kullanıcı kararı 2026-05-20 / P2 PR 6):**
- Bu modül YALNIZ article-level event clustering kapsar.
- **RAPTOR clustering** → `rag/` modülünde (`modules/rag/tasks/raptor.py`;
  Phase 5 mini-cycle ile taşındı — bu PR).
- **Pivot user research clustering** (#1015 `research_clustering.py` +
  `cluster_assigner.py`) → `generations/` modülünde (Phase 6 mini-cycle ile
  taşındı — `modules/generations/tasks/cluster_assigner.py`).
- **`api/admin_clusters.py`** legacy konumunda kalır — `ResearchCluster` +
  `MessageCluster` gözlemi yapar (research domain). Phase 6'da `generations`
  taşınırken birlikte değerlendirilecek.
- `models/research_cluster.py` flat kalır; sahipliği bu PR'da clusters'tan
  generations'a kaydırıldı (master plan §2.4 revize).

Public API (article-event only):
    cluster_article — Celery task entry (called lazily from embedding task,
                      registered via shared/workers/celery_app)
    refresh_clusters — Celery Beat task (hourly)

NOT: admin yüzeyi yok — article-event clustering için legacy `/admin/clusters`
route'u (research_cluster + message_cluster gözlemi) eski yerinde duruyor.

See:
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
"""

__all__: list[str] = []
