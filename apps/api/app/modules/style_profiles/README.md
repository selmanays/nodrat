# `modules/style_profiles/`

**Layer:** middle — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** **active** (Phase 2 — first module migrated).

Kullanıcı yazı tarzı (style profile) analizi domain modülü. Pro+ tier paywall
+ slot quota (Pro=3, Agency=10). PII redaction sample import sırasında
uygulanır (KVKK).

## Layout

- `__init__.py` — public facade (`router` re-export)
- `routes.py` — FastAPI router (URL prefix `/app/style-profiles`)
- `text_metrics.py` — Levenshtein normalize utility (edit distance metric)
- `tasks/style_profile.py` — Celery task `tasks.style_profile.analyze`

## References

- Responsibility + allowed/forbidden imports: [`docs/engineering/modular-monolith-architecture.md`](../../../../docs/engineering/modular-monolith-architecture.md) §3.2
- Boundary decision: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)
- Import direction rules (CI-enforced): [`wiki/decisions/import-direction-rules.md`](../../../../wiki/decisions/import-direction-rules.md)
- Refactor playbook: [`docs/engineering/refactor-playbook.md`](../../../../docs/engineering/refactor-playbook.md)

## Migration history

- 2026-05-20: Phase 2 PR — migrated from `app.api.style_profiles`,
  `app.core.text_metrics`, `app.workers.tasks.style_profile` to this module.
  Behavior-preserving (URL contract `/app/style-profiles/*` unchanged;
  task name `tasks.style_profile.analyze` unchanged).
