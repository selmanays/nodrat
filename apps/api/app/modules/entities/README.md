# `modules/entities/`

**Layer:** middle — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** **active** (Phase 2 — third module migrated).

NER (Named Entity Recognition) + country backfill + entity statistics
domain modülü (#667). LLM-driven entity extraction (DeepSeek) over
article body; persisted as `articles.entities_jsonb`. NER mode
telemetry (`ner_stats`) feeds the retrieval boost decision and is
read by RAG (`core/retrieval.py`, soon `modules/rag/` in Phase 5).

## Layout

- `__init__.py` — public facade (`ner_stats` re-export)
- `ner_stats.py` — in-memory telemetry counter (record / snapshot)
- `tasks/entities.py` — Celery task `tasks.entities.*` (LLM NER + country backfill)

## References

- Locked decision: [`wiki/decisions/ner-pipeline.md`](../../../../wiki/decisions/ner-pipeline.md)
- Architecture: [`docs/engineering/modular-monolith-architecture.md`](../../../../docs/engineering/modular-monolith-architecture.md) §3.2
- Boundary: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)

## Migration history

- 2026-05-20: Phase 2 PR 3 — migrated from `app.core.ner_stats` and
  `app.workers.tasks.entities`. Behavior-preserving (Celery task name
  `tasks.entities.*` unchanged; queue routing `event_queue` unchanged;
  callers `core/retrieval`, `api/admin_rag`, `workers/tasks/embedding`
  updated to new paths).
- 2026-05-20: Phase 1 PR — scaffold created.
