# `modules/ops/`

**Layer:** cross-cutting — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §1.3.

**Status:** Phase 3 (ops sub-cycle) altında **active**. Maintenance Celery tasks taşıması tamamlandı.

## Yapı

```
modules/ops/
├── __init__.py        Module facade (cross-cutting docstring, no router)
├── tasks/
│   ├── __init__.py    Tasks module docstring (6 string-bound task names)
│   └── maintenance.py Celery task definitions (tasks.maintenance.*) — 713 LoC
└── README.md          Bu dosya
```

**Admin route:** YOK — ops'un kendi admin endpoint'i yok. Maintenance task trigger'ları `admin_queue` ve `admin_system` üzerinden.

## Dependency chain

**Storage layer (PR 1a):**
- `app.shared.workers.db_session` — `_get_session_factory`, `_run_async`

**Runtime config:**
- `app.shared.runtime_config.settings_store`

**Model layer (flat):**
- `app.models.article.Article` (cold tier archive scope)

**Legacy (Phase 4+'a kadar):**
- `app.core.maintenance_tracker` — Celery prerun/postrun tracking (lazy)
- `app.core.embedding_binary` — binary quantization (lazy)
- `app.providers.local_embedding` — local SBERT (lazy, reembed_* için)

## Boundary contract

Mevcut 13. contract: **`domain modules must not import ops/`** (Phase 1'den beri var). Ops kendi domain modüllerinden import edebilir; tersi yasak.

**Yeni contract eklenmedi** — mevcut contract zaten ops için doğru yönü kapsıyor.

## Public API

Celery task names (string-bound; registry'de **DEĞİŞMEZ**):

> **#1634:** `cold_tier_archive` / `cold_tier_restore` / `body_html_drop` task'ları
> ve beat schedule'ları KALDIRILDI — ham haber sayfaları (raw_html) saklanmıyor,
> body_html kalıcı saklanır. Aşağıdaki tablo güncel (3 task).

| Task | Trigger | Notes |
|---|---|---|
| `tasks.maintenance.quantize_chunks` | Admin (operator) | binary embedding quantization batch |
| `tasks.maintenance.reembed_chunks` | Admin (operator) | re-embed batch (operator-only) |
| `tasks.maintenance.reembed_agenda_cards` | Admin (operator) | agenda card re-embed |

**Queue routing:** `tasks.maintenance.* → embedding_queue` ([celery_app.py:73](../../workers/celery_app.py))

## Worker registry (post-migration)

`workers/celery_app.py:36`:

```python
celery_app.autodiscover_tasks([
    ...
    "app.modules.ops.tasks.maintenance",   # Phase 3 ops sub-cycle
    ...
])
```

## Veri güvenliği invariant (kullanıcı kuralı)

- `reembed_chunks`, `reembed_agenda_cards`, `quantize_chunks` task'ları **manuel admin trigger** ile çalışır
- Migration sırasında bu task'lardan **HİÇBİRİ MANUEL TETİKLENMEZ**
- Smoke sırasında manual trigger YASAK
- Pre-existing behavior preserved, not modified (git mv 100% similarity)
- Yeni alembic migration YOK, yeni DELETE/TRUNCATE/UPDATE batch YOK

## Smoke acceptance

**Passive (BLOCKING):**
1. Worker registry: 6 `tasks.maintenance.*` task names korundu
2. Queue routing `tasks.maintenance.* → embedding_queue` korundu
3. Beat schedule (`body-html-drop`, `cold-tier-archive`) değişmedi
4. New path `app.modules.ops.tasks.maintenance` import OK + 6 task attr present
5. Old path `app.workers.tasks.maintenance` → ModuleNotFoundError
6. AST audit: maintenance.py runtime sağlam
7. 7 container × 6 pattern × ≥5 dk log scan: 0/0/0/0/0/0

**Active (READ-only) — N/A:**
- Ops admin route YOK; READ-only active smoke step yok.

**Worker natural fire (NON-BLOCKING, ≤15 dk):**
- `body-html-drop` ve `cold-tier-archive` daily fire (pencerede expected olmayabilir)
- Pencerede fire görülürse raporlanır; görülmezse "not observed within 15 min window, non-blocking"

**Manuel trigger: YASAK:**
- `reembed_chunks`, `reembed_agenda_cards`, `quantize_chunks` — KESİNLİKLE TETİKLENMEZ
- Direct DB/Redis YOK

## References

- Boundary: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)
- Import direction: [`wiki/decisions/import-direction-rules.md`](../../../../wiki/decisions/import-direction-rules.md)
- Refactor playbook: [`docs/engineering/refactor-playbook.md`](../../../../docs/engineering/refactor-playbook.md)
- Veri güvenliği: `feedback_embedding_rag_index_safety.md` (memory)
