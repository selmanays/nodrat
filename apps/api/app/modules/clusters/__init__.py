"""Module: clusters

Domain: article-level event clustering. Haber maddelerinin (articles) zaman +
embedding bazlı kümelenmesi (event_cluster + event_article ilişkileri).

**Scope sınırı (kullanıcı kararı 2026-05-20 / P2 PR 6):**
- Bu modül YALNIZ article-level event clustering kapsar.
- **RAPTOR clustering** → `rag/` modülünde kalır (workers/tasks/raptor.py;
  Phase 5'te taşınacak).
- **Pivot user research clustering** (#1015 `research_clustering.py` +
  `cluster_assigner.py`) → `generations/` modülüne ait (Phase 6'da taşınacak).
- `models/research_cluster.py` flat kalır; sahipliği bu PR'da clusters'tan
  generations'a kaydırıldı (master plan §2.4 revize).

Public API:
    admin_router    — FastAPI router (URL prefix `/admin/clusters`)
    cluster_article — Celery task entry (called lazily from embedding task)

See:
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
"""

from app.modules.clusters.admin.routes import router as admin_router

__all__ = ["admin_router"]
