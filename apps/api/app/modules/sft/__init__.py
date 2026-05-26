"""Module: sft

Domain: SLM eğitim veri pipeline (#567, MVP-1.7).

User-action telemetry + KVKK consent gate + PII secondary scan +
nightly Celery ETL → ChatML training_samples + JSONL export.

Public API (T8-PRE-1 sonrası — submodule path):
    `app.modules.sft.admin.routes.router` — admin router (/admin/sft)
    `app.modules.sft.tasks.sft_curator`   — Celery task module (string-bound)
    `app.modules.sft.eligibility`         — SFT/DPO eligibility rules

See:
    wiki/decisions/own-slm-strategy.md
    wiki/decisions/sft-message-source.md
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
    wiki/topics/t8-model-relocation-mini-plan.md §3 hard-stop 11 (lazy `__init__.py`)
"""

# T8-PRE-1 (v68): route eager re-export kaldırıldı (collect-time circular
# import koruması).

__all__: list[str] = []
