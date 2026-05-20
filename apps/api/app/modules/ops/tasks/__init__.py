"""Ops Celery tasks — Phase 3 (ops sub-cycle) altında modules/ops altına taşındı.

Task names AYNEN (string-bound, decorator'dan kanıt):
    tasks.maintenance.cold_tier_archive      — Beat: daily; body_html → MinIO/Contabo
    tasks.maintenance.cold_tier_restore      — admin trigger (operator)
    tasks.maintenance.body_html_drop         — Beat: post-archive cleanup
    tasks.maintenance.quantize_chunks        — admin trigger (binary embedding)
    tasks.maintenance.reembed_chunks         — admin trigger (operator)
    tasks.maintenance.reembed_agenda_cards   — admin trigger (operator)

Queue routing: tasks.maintenance.* → embedding_queue (celery_app.py task_routes)

Beat schedule (active):
    body-html-drop                  → daily (post-archive cleanup)
    cold-tier-archive               → daily (body_html → object storage)

Pre-existing behavior preserved, not modified:
  - cold_tier_archive + body_html_drop pipeline AYNEN (idempotent per-article)
  - reembed_*/quantize_chunks admin trigger sorumluluğu DOKUNULMADI
  - Migration sırasında manuel tetiklenmez (veri güvenliği invariant'ı)
"""
