# `modules/sft/`

**Layer:** middle — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** **active** (Phase 2 — second module migrated).

SFT (Supervised Fine-Tuning) data pipeline domain modülü (#567, MVP-1.7).
User-action telemetry + KVKK consent gate + PII secondary scan +
nightly Celery ETL → ChatML training_samples + JSONL export.

## Layout

- `__init__.py` — public facade (`admin_router` re-export)
- `admin/routes.py` — FastAPI admin router (URL prefix `/admin/sft`)
- `eligibility.py` — SFT/DPO eligibility rules (used by admin route + generations)
- `tasks/sft_curator.py` — Celery nightly ETL task (`tasks.sft_curator.curate_nightly`)

Models stay flat per [models-flat-until-conditions](../../../../wiki/decisions/models-flat-until-conditions.md):
- `app/models/training_sample.py`
- `app/models/eval_run.py`

## References

- Locked decision: [`wiki/decisions/own-slm-strategy.md`](../../../../wiki/decisions/own-slm-strategy.md)
- Locked decision: [`wiki/decisions/sft-message-source.md`](../../../../wiki/decisions/sft-message-source.md)
- Architecture: [`docs/engineering/modular-monolith-architecture.md`](../../../../docs/engineering/modular-monolith-architecture.md) §3.2
- Boundary: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)

## Migration history

- 2026-05-20: Phase 2 PR 2 — migrated from `app.api.admin_sft`,
  `app.core.sft_eligibility`, `app.workers.tasks.sft_curator` to this module.
  Behavior-preserving (URL `/admin/sft/*` unchanged; task names
  `tasks.sft_curator.*` unchanged; Beat `sft-curator-nightly` unchanged).
- 2026-05-20: Phase 1 PR — scaffold created.
