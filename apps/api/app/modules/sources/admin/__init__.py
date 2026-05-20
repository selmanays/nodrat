"""Sources admin route — Phase 3 PR 1b'de modules/sources altına taşındı.

Public API:
    router  — FastAPI APIRouter, mount prefix /admin/sources
"""

from app.modules.sources.admin.routes import router

__all__ = ["router"]
