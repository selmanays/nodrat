"""Module: legal

Domain: takedown / abuse / KVKK md.11 privacy-request public form + admin
moderation (#35). Tek public + bir admin router; `TakedownRequest` model
yaşam döngüsü `modules/legal` sahipliğinde (model `app/models/takedown.py`
altında flat — model relocation Phase N+1).

Static legal content (KVKK aydınlatma, ToS, cookies, privacy, refund) frontend
tarafında yaşar (`apps/web/src/app/legal/*`). Bu modül yalnız **takedown / abuse
/ privacy-request workflow** ile ilgilenir; static content sahibi değildir.

Public API (T8-PRE-1 sonrası — submodule path):
    `app.modules.legal.routes.router`        — public router (/legal)
    `app.modules.legal.routes.admin_router`  — admin router (/admin/legal/requests)

See:
    docs/legal/opinion-integration.md §3.4
    docs/legal/incident-response.md §3
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
    wiki/topics/t8-model-relocation-mini-plan.md §3 hard-stop 11 (lazy `__init__.py`)
"""

# T8-PRE-1 (v68): route eager re-export kaldırıldı (collect-time circular
# import koruması).

__all__: list[str] = []
