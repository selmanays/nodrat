"""Ops Celery tasks — Phase 3 (ops sub-cycle) altında modules/ops altına taşındı.

Task names AYNEN (string-bound, decorator'dan kanıt):
    tasks.maintenance.quantize_chunks        — admin trigger (binary embedding)
    tasks.maintenance.reembed_chunks         — admin trigger (operator)
    tasks.maintenance.reembed_agenda_cards   — admin trigger (operator)

Queue routing: tasks.maintenance.* → embedding_queue (celery_app.py task_routes)

NOT (#1634): cold_tier_archive/cold_tier_restore/body_html_drop + ilgili beat
schedule'ları KALDIRILDI — ham haber sayfaları (raw_html) saklanmıyor; body_html
kalıcı saklanır (re-extract kaynağı olmadan drop güvensizdi).

Migration sırasında manuel tetiklenmez (veri güvenliği invariant'ı).
"""
