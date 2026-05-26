# `modules/sft/`

**Layer:** middle — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** **active** (Phase 2 — second module migrated).

SFT (Supervised Fine-Tuning) data pipeline domain modülü (#567, MVP-1.7).
User-action telemetry + KVKK consent gate + PII secondary scan +
nightly Celery ETL → ChatML training_samples + JSONL export.

## Layout

- `__init__.py` — module facade (lazy — T8-PRE-1 v2 disiplinine uygun; `__all__: list[str] = []`)
- `models.py` — ORM models (`TrainingSample`) — T8-5 v75 sonrası
- `admin/routes.py` — FastAPI admin router (URL prefix `/admin/sft`)
- `eligibility.py` — SFT/DPO eligibility rules (used by admin route + generations)
- `tasks/sft_curator.py` — Celery nightly ETL task (`tasks.sft_curator.curate_nightly`)

> **Not (T8-3 v73):** `EvalRun` ORM modeli artık `modules/rag/models.py`'de (SFT domain'inden RAG benchmark history domain'ine ait — semantik olarak doğru konumda). `modules/sft/` yalnız `TrainingSample` sahipliğinde.

## References

- Locked decision: [`wiki/decisions/own-slm-strategy.md`](../../../../wiki/decisions/own-slm-strategy.md)
- Locked decision: [`wiki/decisions/sft-message-source.md`](../../../../wiki/decisions/sft-message-source.md)
- Architecture: [`docs/engineering/modular-monolith-architecture.md`](../../../../docs/engineering/modular-monolith-architecture.md) §3.2
- Boundary: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)

## Migration history

| PR | Tarih | Değişiklik |
|---|---|---|
| T8-5 | 2026-05-27 | `TrainingSample` ORM model `app/models/training_sample.py` → `app/modules/sft/models.py` (100% rename, history preserved; 141 satır; T8 model relocation Wave B 2/6). `app/models/__init__.py` facade `from app.modules.sft.models import TrainingSample` formuyla re-export ediyor; `from app.models import *` (Alembic env.py:40) korunur. **2 caller flip:** `apps/api/app/modules/sft/tasks/sft_curator.py:41` (nightly ETL ChatML curation) + `apps/api/app/modules/sft/admin/routes.py:39` (admin SFT dataset CRUD). Caller bütçesi 5 dosya (≤ 8). |
| T8-PRE-1 v2 | 2026-05-26 | Modül `__init__.py` lazy disiplinine eklendi (route eager re-export kaldırıldı). |
| Phase 2 PR 2 | 2026-05-20 | Migrated from `app.api.admin_sft`, `app.core.sft_eligibility`, `app.workers.tasks.sft_curator` to this module. Behavior-preserving (URL `/admin/sft/*` unchanged; task names `tasks.sft_curator.*` unchanged; Beat `sft-curator-nightly` unchanged). |
| Phase 1 PR | 2026-05-20 | Scaffold created. |
