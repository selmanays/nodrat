"""Module: entities

Domain: NER (Named Entity Recognition) + country backfill + entity stats (#667).

LLM-driven entity extraction (DeepSeek) over article body; persisted as
`articles.entities_jsonb`. NER mode telemetry (`ner_stats`) feeds the
retrieval boost decision (multi_and / single_rare / no_match) — kept
in-memory, process-lifetime.

Public API:
    ner_stats               — telemetry counter (record, snapshot)
    tasks.entities          — Celery task `tasks.entities.*`

See:
    wiki/decisions/ner-pipeline.md
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
"""

from app.modules.entities import ner_stats

__all__ = ["ner_stats"]
