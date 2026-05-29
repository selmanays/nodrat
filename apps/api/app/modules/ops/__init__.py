"""Module: ops

Layer: cross-cutting (master plan §1.3 — observability, maintenance, lifecycle)
Status: Phase 3 (ops sub-cycle) altında aktif (maintenance tasks taşıması).

Public API:
    tasks   — Celery task module (string-bound: tasks.maintenance.*)

Task surface (6 task — string identity DEĞİŞMEZ):
    tasks.maintenance.cold_tier_archive      — Beat: daily; body_html → MinIO/Contabo
    tasks.maintenance.cold_tier_restore      — admin trigger (operator)
    tasks.maintenance.body_html_drop         — Beat: post-archive cleanup
    tasks.maintenance.quantize_chunks        — admin trigger (binary embedding)
    tasks.maintenance.reembed_chunks         — admin trigger (operator)
    tasks.maintenance.reembed_agenda_cards   — admin trigger (operator)

Storage dependency:
    `app.shared.workers.db_session` (Phase 3 PR 1a)
    `app.shared.runtime_config.settings_store`
    `app.modules.articles.models` — Article (T8-12b: 2026-05-28 taşındı)

Legacy dependencies (Phase 4+'a kadar):
    `app.core.storage` — MinIO/Contabo client
    `app.core.maintenance_tracker` — Celery prerun/postrun tracking
    `app.core.embedding_binary` — binary quantization (lazy)
    `app.providers.local_embedding` — local SBERT (lazy)

Boundary:
    Cross-cutting layer — `domain modules must not import ops/` contract var (PR Phase 1).
    Ops domain modules'lerden istediği gibi import edebilir; tersi yasak.

Admin route: YOK (ops kendi admin endpoint'i yok; bunlar admin_queue/admin_system'da).

See:
- wiki/plans/modular-monolith-transition-master-plan.md §1.3
- wiki/decisions/modular-monolith-boundary.md
"""
