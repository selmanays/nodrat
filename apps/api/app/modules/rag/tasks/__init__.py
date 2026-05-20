"""RAG Celery tasks — Phase 5 mini-cycle başlangıcı (raptor taşımasıyla aktive).

Task names AYNEN (string-bound, decorator'dan kanıt):
    tasks.raptor.build_weekly_summary_cards — bind=True (haftalık RAPTOR-Lite hierarchical)

Queue routing: tasks.raptor.* → event_queue (worker_rag tüketir)

Beat schedule:
    raptor-build-weekly-summary (haftalık) — tasks.raptor.build_weekly_summary_cards

Pre-existing behavior preserved, not modified:
  - daily_cards UPSERT pipeline AYNEN
  - weekly cluster building algoritması DOKUNULMADI
  - country aggregation logic (_aggregate_country) DOKUNULMADI
  - Manual trigger: admin endpoint /admin/rag/raptor/trigger (direct async, Celery dispatch DEĞİL)
"""
