# `modules/style_profiles/`

**Layer:** middle — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** **active** (Phase 2 — first module migrated).

Kullanıcı yazı tarzı (style profile) analizi domain modülü. Pro+ tier paywall
+ slot quota (Pro=3, Agency=10). PII redaction sample import sırasında
uygulanır (KVKK).

## Layout

- `__init__.py` — module facade (lazy — T8-PRE-1 v2 disiplinine uygun; `__all__: list[str] = []`)
- `models.py` — ORM models (`StyleProfile`, `StyleSample`) — T8-6 v76 sonrası
- `routes.py` — FastAPI router (URL prefix `/app/style-profiles`)
- `text_metrics.py` — Levenshtein normalize utility (edit distance metric)
- `tasks/style_profile.py` — Celery task `tasks.style_profile.analyze`

## References

- Responsibility + allowed/forbidden imports: [`docs/engineering/modular-monolith-architecture.md`](../../../../docs/engineering/modular-monolith-architecture.md) §3.2
- Boundary decision: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)
- Import direction rules (CI-enforced): [`wiki/decisions/import-direction-rules.md`](../../../../wiki/decisions/import-direction-rules.md)
- Refactor playbook: [`docs/engineering/refactor-playbook.md`](../../../../docs/engineering/refactor-playbook.md)

## Migration history

| PR | Tarih | Değişiklik |
|---|---|---|
| T8-6 | 2026-05-27 | `StyleProfile` + `StyleSample` ORM models `app/models/style_profile.py` → `app/modules/style_profiles/models.py` (100% rename, 123 satır, history preserved; T8 model relocation Wave B 3/6). `app/models/__init__.py` facade `from app.modules.style_profiles.models import StyleProfile, StyleSample` formuyla re-export ediyor. **3 caller flip:** `app/api/app_research_stream.py:240` (lazy import — Pro+ paywall style-driven generation context), `style_profiles/routes.py:34` (CRUD + analyzer trigger), `style_profiles/tasks/style_profile.py:33` (Celery analyzer task). Caller bütçesi 6 dosya (≤ 8). |
| T8-PRE-1 v2 | 2026-05-26 | Modül `__init__.py` lazy disiplinine eklendi. |
| Phase 2 PR | 2026-05-20 | Migrated from `app.api.style_profiles`, `app.core.text_metrics`, `app.workers.tasks.style_profile` to this module. Behavior-preserving (URL contract `/app/style-profiles/*` unchanged; task name `tasks.style_profile.analyze` unchanged). |
