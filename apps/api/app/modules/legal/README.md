# `modules/legal/`

**Layer:** parallel — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** **active** (Phase 2 — fourth module migrated).

Takedown / abuse / KVKK md.11 privacy-request public form + admin
moderation domain modülü (#35). `TakedownRequest` workflow sahibi —
service/repository ayrı dosya gerektirmiyor (mevcut route + helper'lar
tek dosyada yeterli; yapay abstraction yok).

## Layout

- `__init__.py` — module facade (lazy — T8-PRE-1 v2 disiplinine uygun; `__all__: list[str] = []`)
- `models.py` — ORM models (`TakedownRequest`) — T8-4 v74 sonrası
- `routes.py` — FastAPI public + admin router'lar (URL: `/legal/*` + `/admin/legal/requests/*`)

## Ne yapar / yapmaz

| Yapar | Yapmaz |
|---|---|
| Takedown / abuse / copyright / KVKK md.11 form ingest | KVKK aydınlatma / ToS / cookies static content (frontend `apps/web/src/app/legal/*`) |
| Public POST + admin GET/PATCH moderation | User auth / consent (accounts domain) |
| `TakedownRequest` model yaşam döngüsü | Crawler/scraping content takedown (crawler domain) |

## Endpoints (URL contract — değişmez)

Public:
- `POST /legal/abuse`
- `POST /legal/takedown` (5651)
- `POST /legal/copyright` (FSEK)
- `POST /legal/privacy-request` (KVKK md.11)

Admin:
- `GET /admin/legal/requests`
- `GET /admin/legal/requests/{ticket_id}`
- `PATCH /admin/legal/requests/{ticket_id}`

## References

- Architecture: [`docs/engineering/modular-monolith-architecture.md`](../../../../docs/engineering/modular-monolith-architecture.md) §3.4
- Locked decision: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md) (takedown service/repo legal sahipliği)
- Boundary: [`wiki/decisions/import-direction-rules.md`](../../../../wiki/decisions/import-direction-rules.md)
- Source: [`docs/legal/opinion-integration.md`](../../../../docs/legal/opinion-integration.md) §3.4
- Source: [`docs/legal/incident-response.md`](../../../../docs/legal/incident-response.md) §3 (24h SLA)

## Migration history

| PR | Tarih | Değişiklik |
|---|---|---|
| T8-4 | 2026-05-27 | `TakedownRequest` ORM model `app/models/takedown.py` → `app/modules/legal/models.py` (100% rename, history preserved; 145 satır; T8 model relocation Wave B 1/6). `app/models/__init__.py` facade `from app.modules.legal.models import TakedownRequest` formuyla re-export ediyor; `from app.models import *` (Alembic env.py:40) korunur. **2 caller flip:** `app/api/app_me.py:51` (KVKK privacy-request endpoint) + `app/modules/legal/routes.py:36` (public+admin handlers). Caller bütçesi 5 dosya (≤ 8). |
| T8-PRE-1 v2 | 2026-05-26 | Modül `__init__.py` lazy disiplinine eklendi (route eager re-export kaldırıldı; collect-time circular import koruması). |
| Phase 2 PR 4 | 2026-05-20 | Migrated from `app.api.legal` (470 satır tek dosya). Behavior-preserving (URL contract korunur; 4 public + 3 admin endpoint unchanged). Test file import paths updated. |
| Phase 1 PR | 2026-05-20 | Scaffold created. |
