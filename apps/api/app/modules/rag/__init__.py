"""Module: rag

Layer: middle (master plan §2 — clusters üstü, generations altı; retrieval + ranking
+ weekly RAPTOR summary)

Status: Phase 5 mini-cycle başladı; raptor task taşımasıyla aktive (Phase 5 full
migration retrieval pipeline + chunker + ranking + admin_rag ileride genişler).

Public API (mevcut):
    tasks   — Celery task module (string-bound: tasks.raptor.*)

Future surface (Phase 5 genişlemeleri):
    retrieval/ranking core, chunker, RAG pipeline orchestrator, admin_rag (kısmi)

Boundary:
    Middle layer; clusters/embedding üstü, generations altı; modular contract'larda
    rag → crawler/generations YASAK (mevcut 13 contract korunur).

See:
- wiki/plans/modular-monolith-transition-master-plan.md §2 / §12.2
- wiki/decisions/modular-monolith-boundary.md
- wiki/decisions/import-direction-rules.md
"""
