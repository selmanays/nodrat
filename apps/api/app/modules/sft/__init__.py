"""Module: sft

Domain: SLM eğitim veri pipeline (#567, MVP-1.7).

User-action telemetry + KVKK consent gate + PII secondary scan +
nightly Celery ETL → ChatML training_samples + JSONL export.

Public API:
    admin_router    — FastAPI router (URL prefix `/admin/sft`)
    sft_curator     — Celery task module (name `tasks.sft_curator.*`)
    eligibility     — SFT/DPO eligibility rules

See:
    wiki/decisions/own-slm-strategy.md
    wiki/decisions/sft-message-source.md
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
"""

from app.modules.sft.admin.routes import router as admin_router

__all__ = ["admin_router"]
