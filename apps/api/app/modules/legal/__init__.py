"""Module: legal

Domain: takedown / abuse / KVKK md.11 privacy-request public form + admin
moderation (#35). Tek public + bir admin router; `TakedownRequest` model
yaşam döngüsü `modules/legal` sahipliğinde (model `app/models/takedown.py`
altında flat — model relocation Phase N+1).

Static legal content (KVKK aydınlatma, ToS, cookies, privacy, refund) frontend
tarafında yaşar (`apps/web/src/app/legal/*`). Bu modül yalnız **takedown / abuse
/ privacy-request workflow** ile ilgilenir; static content sahibi değildir.

Public API:
    router          — FastAPI router (URL prefix `/legal`)
    admin_router    — FastAPI router (URL prefix `/admin/legal/requests`)

See:
    docs/legal/opinion-integration.md §3.4
    docs/legal/incident-response.md §3
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
"""

from app.modules.legal.routes import admin_router, router

__all__ = ["admin_router", "router"]
