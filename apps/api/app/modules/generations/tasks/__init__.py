"""Generations Celery tasks — agenda taşımasıyla aktive.

Task names AYNEN (string-bound, decorator'dan kanıt):
    tasks.agenda.generate_agenda_card     — bind=True; cluster article-event card
    tasks.agenda.refresh_active_cards     — Beat: saatlik
    tasks.agenda.backfill_country         — Beat: batch country backfill

Queue routing: tasks.agenda.* → event_queue (celery_app.py task_routes)

Beat schedule:
    refresh-agenda-cards    — saatlik
    backfill-country        — batch

Pre-existing behavior preserved, not modified:
  - agenda card UPSERT pipeline AYNEN (idempotent per-cluster)
  - UPDATE agenda_cards SET country WHERE id=:id (per-row, batch DEĞİL) DOKUNULMADI
  - Manual trigger yapılmaz (Beat-driven + clusters chain dispatch)
"""
