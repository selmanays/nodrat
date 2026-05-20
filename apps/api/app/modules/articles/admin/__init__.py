"""Articles admin route — Phase 3 PR 2b'de modules/articles altına taşındı.

Public API:
    router  — FastAPI APIRouter, mount prefix /admin/articles
"""

from app.modules.articles.admin.routes import router

__all__ = ["router"]
