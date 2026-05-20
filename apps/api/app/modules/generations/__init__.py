"""Module: generations

Layer: upper (master plan §1.3 — rag'ın üstü; final answer generation + agenda + research)
Status: Phase 6 mini-cycle başladı; agenda tasks taşımasıyla aktive (Phase 6 god-file
pipeline app_research_stream + admin_research + frontend ile ileride genişler).

Public API (mevcut):
    tasks   — Celery task module (string-bound: tasks.agenda.*)

Future surface (Phase 6 genişlemeleri):
    research routes, SSE streaming, conversation context, research_cluster gözlem

Boundary:
    Upper layer; rag/clusters/embedding/articles upper layer'a import etmez
    (mevcut forbidden contracts). Generations rag/sft'e import edebilir.

See:
- wiki/plans/modular-monolith-transition-master-plan.md §1.3 / §12.2
- wiki/decisions/modular-monolith-boundary.md
- wiki/decisions/import-direction-rules.md
"""
