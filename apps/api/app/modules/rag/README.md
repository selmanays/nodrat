# `modules/rag/`

**Layer:** middle — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** Phase 5 mini-cycle başladı (raptor task aktive). Tam Phase 5 migration (retrieval + chunker + ranking + admin_rag) ileride.

## Yapı

```
modules/rag/
├── __init__.py        Module facade (middle-layer docstring, no router)
├── tasks/
│   ├── __init__.py    Tasks module docstring (1 string-bound raptor task name)
│   └── raptor.py      Celery task definition (tasks.raptor.*) — 460 LoC
└── README.md          Bu dosya
```

**Admin route:** YOK bu PR'da. Phase 5 full migration'da admin_rag (kısmi) eklenir.

## Dependency chain

- `app.shared.workers.db_session` — `_run_async`, `open_session`
- `app.shared.runtime_config.prompts_store` (lazy)
- `app.shared.runtime_config.settings_store` (lazy)
- `app.models.{agenda, event, daily_card}` (flat models)
- `app.providers.{base, registry}` (provider layer)
- `app.core.cost_tracker.track_provider_call` (legacy)
- `app.prompts.weekly_summary` (legacy prompts — Phase 5 full migrate'te modüle taşınır)

**Cross-module references:** YOK. Task Beat-driven + 1 admin endpoint direct async call (NOT Celery dispatch).

## Boundary contract

Mevcut 13 contract'ta `app.modules.rag` çeşitli "forbidden" listelerinde (crawler/embedding → rag YASAK; rag → crawler/generations YASAK). Rag için **kaynak contract henüz YOK** — Phase 5 full migration zincirinde tasarlanacak.

**Yeni contract eklenmedi.** Yeni `ignore_imports` eklenmedi.

## Public API

Celery task names (string-bound; registry'de **DEĞİŞMEZ**):

| Task | Trigger | Notes |
|---|---|---|
| `tasks.raptor.build_weekly_summary_cards` | Beat (haftalık) + admin trigger (direct async) | bind=True; daily_cards + weekly clusters UPSERT |

**Queue routing:** `tasks.raptor.* → event_queue` (worker_rag tüketir)

**Admin trigger:** `POST /admin/rag/raptor/trigger` `_build_weekly_summary_cards_async` direct `await` (NOT Celery dispatch — A1 decoupling GEREK YOK).

## Veri güvenliği invariant (kullanıcı kuralı)

- `daily_cards` UPSERT pipeline AYNEN (idempotent per-day)
- `weekly_cluster_cards` UPSERT pipeline AYNEN (idempotent per-week)
- `_aggregate_country` algoritması DOKUNULMADI
- Manual trigger smoke'ta YOK (admin endpoint var ama production state-changing smoke kullanılmaz)
- Pre-existing behavior preserved, not modified

## Smoke acceptance

**Passive (BLOCKING):**
1. Worker registry (worker_rag, force-load): 1 `tasks.raptor.*` task korundu
2. Queue routing `tasks.raptor.* → event_queue` korundu
3. Beat (raptor-build-weekly-summary, haftalık) değişmedi
4. New path `app.modules.rag.tasks.raptor` import OK + 1 task attr + `_aggregate_country` + `_build_weekly_summary_cards_async` helper visible
5. Old path `app.workers.tasks.raptor` → `ModuleNotFoundError`
6. 7 container × 6 pattern × ≥5 dk log scan: 0 hits

**Worker natural fire (NON-BLOCKING):**
- Beat schedule haftalık — pencerede fire BEKLENMEZ → "not observed, non-blocking"

**Manuel trigger YASAK** (admin endpoint var ama production state-changing smoke kullanılmaz).

## Smoke probe disipline (#1141/#1142 dersi)

Worker container'da `celery_app.tasks` registry programatik sorgu YAPILMAZSA boş görünür (Celery `include` auto-load yalnız `celery worker` command init'inde tetiklenir). Doğru sorgu:

```python
from app.workers.celery_app import celery_app
celery_app.loader.import_default_modules()   # ← GEREK
print([t for t in celery_app.tasks if "raptor" in t])
```

## References

- [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)
- [`wiki/decisions/import-direction-rules.md`](../../../../wiki/decisions/import-direction-rules.md)
- [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2 / §12.2
- Locked decision (raptor → rag/): `apps/api/app/modules/clusters/__init__.py` L8-9
