"""Module: entities

Domain: NER (Named Entity Recognition) + country backfill (#667).

LLM-driven entity extraction (DeepSeek) over article body; persisted as
`articles.entities_jsonb`.

Public API:
    tasks.entities          — Celery task `tasks.entities.*`

NER mode telemetry (telemetri counter): taşındı `app.shared.observability.ner_stats`
(Phase 8 PR-8a-3 — Layer 0 saflığı; core/retrieval.py + api/admin_rag.py her
ikisi de read-side consumer'dır, pure infra telemetry primitive).

See:
    wiki/decisions/ner-pipeline.md
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
"""

__all__: list[str] = []
