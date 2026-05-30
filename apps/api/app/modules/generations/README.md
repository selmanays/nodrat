# `modules/generations/`

**Layer:** upper — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §1.3.

**Status:** Phase 6 mini-cycle ilerliyor (agenda + cluster_assigner tasks aktive). Tam Phase 6 migration (app_research_stream SSE god-file + admin_research + frontend) ileride.

## Yapı

```
modules/generations/
├── __init__.py             Module facade (upper-layer docstring, no router)
├── models.py               ResearchCluster + MessageCluster (T8-9) + ResearchCacheTelemetry (T8-15) ORM — moved 2026-05-28
├── services/
│   ├── __init__.py         Services module docstring (lazy, no eager import)
│   ├── research_cache_telemetry.py  #981 telemetri yazıcı (T7-4: moved 2026-05-28 from app/core/research_cache_telemetry.py)
│   └── conversation_context.py  #793 S2 context assembly read-only (T7-5: moved 2026-05-28 from app/core/conversation_context.py)
├── tasks/
│   ├── __init__.py         Tasks module docstring (5 string-bound task names)
│   ├── agenda.py           tasks.agenda.* — 537 LoC (agenda card pipeline)
│   └── cluster_assigner.py tasks.research_clustering.* — 350 LoC (pivot user research clustering)
└── README.md               Bu dosya
```

## Migration history

- 2026-05-28: **T8-15** — `ResearchCacheTelemetry` ORM modeli (#981 prompt-cache segment
  ledger) `app/models/research_cache_telemetry.py`'den `models.py`'e taşındı (92 satır;
  ResearchCluster + MessageCluster yanına). **T8 restart 1. harvest PR'ı** — T7-4 ile
  service generations'a taşınmıştı; şimdi model de generations'a gelince zincir TAM
  (service same-module `from app.modules.generations.models import ResearchCacheTelemetry`).
  Facade `app/models/__init__.py` re-export `generations/models`'e güncellendi (T8-9 satırına
  eklendi). Service lazy import (`:95`) same-module path'e flip edildi. **Caller:** 2 (facade
  + service lazy); test caller 0. **`relationship()` YOK** (FK by string "users.id") →
  mapper 3/3 PASS. **Circular YOK**, **import-linter 16/16**. Behavior-preserving; ORM tanımı
  birebir (tablo/4 index/KVKK token-only AYNEN); no migration, no schema change. **T8 10/22 → 11/22.**

- 2026-05-28: **T7-5** — `conversation_context.py` (#793 S2 conversation context helpers)
  `app/core/conversation_context.py`'den `services/conversation_context.py`'e taşındı
  (100% rename, 473 satır). **Gerekçe:** service `Conversation` + `Message` modellerini
  EAGER (top-level :26) import ediyor; core/'ta kalması T8-10 (Conversation+Message →
  conversations YENİ modül) relocation'ını `core/* must not import modules/*` ile
  blocklardı → generations domain'e taşındı, **son core/ consumer kaldırıldı** (0 başka
  core/ importer). 4 caller flip: `api/_research_stream_context.py:37` +
  `api/app_research_stream.py:44` + `modules/generations/tasks/cluster_assigner.py:41`
  (hepsi eager) + `tests/unit/test_l1_windowed_context.py:14`. **Read-only** (db.add/commit
  YOK); `relationship()` YOK (yalnız query join). **Circular risk YOK** (generations/models
  services'i import etmez; facade generations/models import eder, services değil). **T8-10
  TAM unblock**. T7 core-consumer cleanup 5. PR. Behavior-preserving; research stream context
  assembly (#793 S2) AYNEN; no migration, no schema change.

- 2026-05-28: **T7-4** — `research_cache_telemetry.py` (#981 telemetri yazıcı)
  `app/core/research_cache_telemetry.py`'den `services/research_cache_telemetry.py`'e
  taşındı (100% rename, 134 satır). NEW `services/` alt-paket (lazy). **Gerekçe:**
  service `ResearchCacheTelemetry` modelini (lazy, fonksiyon-gövdesi) import ediyor;
  core/'ta kalması T8-15 (ResearchCacheTelemetry → `models.py`) relocation'ını
  `core/* must not import modules/*` ile blocklardı → generations domain'e taşındı,
  core/ consumer kaldırıldı. 3 caller flip: `api/app_research_stream.py:540` (lazy,
  research SSE telemetri çağrısı) + `tests/unit/test_research_cache_telemetry.py:13`
  (eager import) + `tests/unit/test_research_stream_tracked_chat_generate.py:152`
  (string-target `patch()` → yeni path; generations purge-list A-grubunda DEĞİL →
  T7-3 dersi tetiklenmez). T7 core-consumer cleanup 4. PR; **T8-15 unblock**.
  Behavior-preserving; izole tablo (`research_cache_telemetry`) + KVKK
  token-sayısı-only + best-effort writer (#981) AYNEN; no migration, no schema change.

- 2026-05-28: **T8-9** — `ResearchCluster` + `MessageCluster` ORM modelleri
  `app/models/research_cluster.py`'den `models.py`'e taşındı (100% rename, 149 satır).
  Master plan §2.4 revize (2026-05-20) ownership = generations kararı uygulandı.
  3 caller flip: `api/admin_clusters.py:32` (admin observation route, legacy
  location) + `api/app_me.py:50` (#1016 Pivot Faz 3b — kullanıcı araştırma
  ilgi alanları salt-okuma) + `modules/generations/tasks/cluster_assigner.py:52`
  (same-module same-domain flip). Wave C continued (v78 Option B FAIL sonrası
  T8 risk-classified mode altında 2. başarılı safe candidate). Behavior-preserving;
  veri güvenliği invariant korunur (`research_clusters` + `message_clusters`
  tablolarına dokunulmadı; raw SQL caller yok; UPSERT pipeline AYNEN; parent
  edges hierarchy AYNEN).

**Admin route:** YOK bu PR'da. Phase 6 full migration'da admin_research route eklenir.

## Dependency chain

**agenda.py:**
- `app.shared.workers.db_session` — `_run_async`, `open_session`
- `app.shared.runtime_config.prompts_store` (lazy)
- `app.shared.runtime_config.settings_store` (lazy)
- `app.models.{agenda, event}` (flat models)
- `app.providers.{base, registry}` (provider layer)
- `app.shared.observability.cost_tracker.track_provider_call` (legacy)
- `app.prompts.{agenda_card, country_backfill}` (legacy prompts)

**cluster_assigner.py:**
- `app.shared.workers.db_session` — `_run_async`, `open_session`
- `app.core.research_clustering` — pure logic (algorithm core, no task deps)
- `app.models.{research_cluster, message_cluster}` (flat models)
- `app.providers.{base, registry}` (provider layer)
- `app.shared.observability.cost_tracker.track_provider_call` (legacy)

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
