# `modules/generations/`

**Layer:** upper — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §1.3.

**Status:** Phase 6 mini-cycle ilerliyor (agenda + cluster_assigner tasks aktive). Tam Phase 6 migration (app_research_stream SSE god-file + admin_research + frontend) ileride.

## Yapı

```
modules/generations/
├── __init__.py             Module facade (upper-layer docstring, no router)
├── tasks/
│   ├── __init__.py         Tasks module docstring (5 string-bound task names)
│   ├── agenda.py           tasks.agenda.* — 537 LoC (agenda card pipeline)
│   └── cluster_assigner.py tasks.research_clustering.* — 350 LoC (pivot user research clustering)
└── README.md               Bu dosya
```

**Admin route:** YOK bu PR'da. Phase 6 full migration'da admin_research route eklenir.

## Dependency chain

**agenda.py:**
- `app.shared.workers.db_session` — `_run_async`, `open_session`
- `app.shared.runtime_config.prompts_store` (lazy)
- `app.shared.runtime_config.settings_store` (lazy)
- `app.models.{agenda, event}` (flat models)
- `app.providers.{base, registry}` (provider layer)
- `app.core.cost_tracker.track_provider_call` (legacy)
- `app.prompts.{agenda_card, country_backfill}` (legacy prompts)

**cluster_assigner.py:**
- `app.shared.workers.db_session` — `_run_async`, `open_session`
- `app.core.research_clustering` — pure logic (algorithm core, no task deps)
- `app.models.{research_cluster, message_cluster}` (flat models)
- `app.providers.{base, registry}` (provider layer)
- `app.core.cost_tracker.track_provider_call` (legacy)

**Cross-module references:** YOK. Tasks Beat-driven veya chain dispatch (PR #1140 send_task pattern).

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
| `tasks.research_clustering.assign` | Beat (gece) | pivot user research clustering (#1015) |
| `tasks.research_clustering.refine_hierarchy` | Beat (gece) | hierarchy refine (parent edges) |

**Queue routing:**
- `tasks.agenda.* → event_queue`
- `tasks.research_clustering.* → embedding_queue`

(celery_app.py task_routes)

## Veri güvenliği invariant (kullanıcı kuralı)

- `agenda_cards` UPSERT pipeline AYNEN (idempotent per-cluster)
- `UPDATE agenda_cards SET country WHERE id=:id` (per-row, batch DEĞİL) DOKUNULMADI
- `research_cluster` + `message_cluster` UPSERT pipeline AYNEN (idempotent per-message)
- `core/research_clustering` algorithm core (parent edges, hierarchy) DOKUNULMADI
- Manual trigger smoke'ta YOK
- Pre-existing behavior preserved, not modified

## Smoke acceptance

**Passive (BLOCKING):**
1. Worker registry: 5 task korundu (3 `tasks.agenda.*` + 2 `tasks.research_clustering.*`)
2. Queue routing `tasks.agenda.* → event_queue` + `tasks.research_clustering.* → embedding_queue` korundu
3. Beat (4 schedule: refresh-agenda-cards, backfill-country, research-clustering-assign, research-clustering-refine-hier) değişmedi
4. New path import OK:
   - `app.modules.generations.tasks.agenda` + 3 task attr
   - `app.modules.generations.tasks.cluster_assigner` + 2 task attr
5. Old path `app.workers.tasks.{agenda,cluster_assigner}` → ModuleNotFoundError
6. 7 container × 6 pattern × ≥5 dk log scan: 0 hits

**Worker natural fire (NON-BLOCKING, ≤15 dk):**
- agenda: pencerede cluster_article succeeded ise `tasks.agenda.generate_agenda_card` succeeded log
- cluster_assigner: Beat gece tetiklenir; 15dk pencerede fire beklenmez → "not observed, non-blocking"

**Manuel trigger YASAK.**

## References

- [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)
- [`wiki/decisions/import-direction-rules.md`](../../../../wiki/decisions/import-direction-rules.md)
- [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §1.3 / §12.2
