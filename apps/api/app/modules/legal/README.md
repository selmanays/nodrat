# `modules/legal/`

**Layer:** parallel — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** **active** (Phase 2 — fourth module migrated).

Takedown / abuse / KVKK md.11 privacy-request public form + admin
moderation domain modülü (#35). `TakedownRequest` workflow sahibi —
service/repository ayrı dosya gerektirmiyor (mevcut route + helper'lar
tek dosyada yeterli; yapay abstraction yok).

## Layout

- `__init__.py` — public facade (`router` + `admin_router` re-export)
- `routes.py` — FastAPI public + admin router'lar (URL: `/legal/*` + `/admin/legal/requests/*`)

Model stays flat per [models-flat-until-conditions](../../../../wiki/decisions/models-flat-until-conditions.md):
- `app/models/takedown.py` (`TakedownRequest`) — Phase N+1'e kadar flat. Sahibi `legal/` modülü.

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

- 2026-05-20: Phase 2 PR 4 — migrated from `app.api.legal` (470 satır tek dosya).
  Behavior-preserving (URL contract korunur; 4 public + 3 admin endpoint
  unchanged). Test file import paths updated.
- 2026-05-20: Phase 1 PR — scaffold created.
