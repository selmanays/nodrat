# `modules/generations/`

**Layer:** upper — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §1.3.

**Status:** Phase 6 mini-cycle başladı (agenda tasks aktive). Tam Phase 6 migration (app_research_stream SSE god-file + admin_research + frontend) ileride.

## Yapı

```
modules/generations/
├── __init__.py        Module facade (upper-layer docstring, no router)
├── tasks/
│   ├── __init__.py    Tasks module docstring (3 string-bound agenda task names)
│   └── agenda.py      Celery task definitions (tasks.agenda.*) — 537 LoC
└── README.md          Bu dosya
```

**Admin route:** YOK bu PR'da. Phase 6 full migration'da admin_research route eklenir.

## Dependency chain

- `app.shared.workers.db_session` — `_run_async`, `open_session`
- `app.shared.runtime_config.prompts_store` (lazy)
- `app.shared.runtime_config.settings_store` (lazy)
- `app.models.{agenda, event}` (flat models)
- `app.providers.{base, registry}` (provider layer)
- `app.core.cost_tracker.track_provider_call` (legacy)
- `app.prompts.{agenda_card, country_backfill}` (legacy prompts)

**Cross-module references:** Bu PR'da YOK (sources/clusters chain dispatch artık send_task ile — PR #1140 A1 decoupling sonrası).

## Boundary contract

Mevcut 13 contract'ta `app.modules.generations` çeşitli "forbidden" listelerinde (rag/crawler/embedding/clusters/articles → generations YASAK). Generations için **kaynak contract henüz YOK** — Phase 6 full migration zincirinde tasarlanacak.

**Yeni contract eklenmedi.** Yeni `ignore_imports` eklenmedi.

## Public API

Celery task names (string-bound; registry'de **DEĞİŞMEZ**):

| Task | Trigger | Notes |
|---|---|---|
| `tasks.agenda.generate_agenda_card` | clusters chain dispatch (PR #1140 A1 sonrası send_task) | bind=True, max_retries=2; per-cluster |
| `tasks.agenda.refresh_active_cards` | Beat (saatlik) | active card UPSERT cycle |
| `tasks.agenda.backfill_country` | Beat (batch) | country field backfill |

**Queue routing:** `tasks.agenda.* → event_queue` ([celery_app.py:70](../../workers/celery_app.py))

## Veri güvenliği invariant (kullanıcı kuralı)

- `agenda_cards` UPSERT pipeline AYNEN (idempotent per-cluster)
- `UPDATE agenda_cards SET country WHERE id=:id` (per-row, batch DEĞİL) DOKUNULMADI
- Manual trigger smoke'ta YOK
- Pre-existing behavior preserved, not modified

## Smoke acceptance

**Passive (BLOCKING):**
1. Worker registry: 3 `tasks.agenda.*` task korundu
2. Queue routing `tasks.agenda.* → event_queue` korundu
3. Beat (refresh-agenda-cards, backfill-country) değişmedi
4. New path `app.modules.generations.tasks.agenda` import OK + 3 task attr
5. Old path `app.workers.tasks.agenda` → ModuleNotFoundError
6. 7 container × 6 pattern × ≥5 dk log scan: 0 hits

**Worker natural fire (NON-BLOCKING, ≤15 dk):**
- Pencerede yeni cluster_article succeeded ise clusters.send_task → worker'da `tasks.agenda.generate_agenda_card` succeeded log
- 15 dk içinde fire yoksa "not observed, non-blocking"

**Manuel trigger YASAK.**

## References

- [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)
- [`wiki/decisions/import-direction-rules.md`](../../../../wiki/decisions/import-direction-rules.md)
- [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §1.3 / §12.2
