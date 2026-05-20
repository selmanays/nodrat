"""Generations Celery tasks — agenda + cluster_assigner taşımalarıyla aktive.

Task names AYNEN (string-bound, decorator'dan kanıt):
    tasks.agenda.generate_agenda_card        — bind=True; cluster article-event card
    tasks.agenda.refresh_active_cards        — Beat: saatlik
    tasks.agenda.backfill_country            — Beat: batch country backfill
    tasks.research_clustering.assign         — Beat: gece (pivot user research clustering)
    tasks.research_clustering.refine_hierarchy — Beat: gece (hierarchy refine)

Queue routing:
    tasks.agenda.*               → event_queue
    tasks.research_clustering.*  → embedding_queue

Beat schedule:
    refresh-agenda-cards               — saatlik (tasks.agenda.refresh_active_cards)
    backfill-country                   — batch (tasks.agenda.backfill_country)
    research-clustering-assign         — gece (tasks.research_clustering.assign)
    research-clustering-refine-hier    — gece (tasks.research_clustering.refine_hierarchy)

Pre-existing behavior preserved, not modified:
  - agenda_cards UPSERT pipeline AYNEN (idempotent per-cluster)
  - UPDATE agenda_cards SET country WHERE id=:id (per-row, batch DEĞİL) DOKUNULMADI
  - research clustering algoritma (core/research_clustering) DOKUNULMADI
  - Manual trigger yapılmaz (Beat-driven + clusters chain dispatch)
"""
