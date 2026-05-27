# `modules/agenda/`

**Layer:** middle — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.4.

**Status:** Phase 1 + T8-10 (2026-05-28) — scaffold + ORM aktif. Tasks/admin/routes ileride.

Agenda card generation domain modülü. Event cluster bazlı günlük gündem kartı pipeline'ı (#21). Phase 8.2 PR-8.2-11'de pgvector `Vector(1024)` embedding kolonu ORM'e eklendi.

## Scope sınırı

Bu modül **AgendaCard ORM modelini** ve (ileride) agenda generation admin surface'ını kapsar. Kullanıcı locked decision (2026-05-26 v67) ile `agenda` AYRI modül olarak konumlanır (master plan §2.4); `generations/` üst katman olarak agenda tasks tüketir ama AgendaCard ORM sahipliği bu modüldedir.

| Yer almaz | Nedeni | Konumu |
|---|---|---|
| **agenda Celery tasks** (`tasks.agenda.*`) | Phase 6 mini-cycle generations upper-layer'da scaffold edildi | `modules/generations/tasks/agenda.py` |
| **agenda admin route** | Henüz scaffold edilmedi | Future phase |

## Layout

```
modules/agenda/
├── __init__.py    Module facade (lazy; docstring + __all__: list[str] = [])
├── models.py      AgendaCard ORM (T8-10: moved 2026-05-28 from app/models/agenda.py)
└── README.md      Bu dosya
```

## Public API

| Symbol | Type | Note |
|---|---|---|
| `AgendaCard` | ORM model | `agenda_cards` tablosu; event_clusters FK (CASCADE); self-referential parent FK; Vector(1024) embedding (Phase 8.2-11) |

## Dependency chain

**models.py:**
- `app.models.base` — `Base` declarative
- `pgvector.sqlalchemy.Vector` — pgvector type
- `sqlalchemy` + `sqlalchemy.dialects.postgresql` (JSONB, UUID)
- `sqlalchemy.orm` (Mapped, mapped_column)

**FK references (by table name — class location agnostic):**
- `event_clusters.id` (CASCADE) — table owned by `modules/clusters/models.py` (T8-8)
- `agenda_cards.id` (SET NULL, self-ref parent)

**No `relationship()` calls** — yalnız FK column declarations (T8 hard kural — `relationship()` string-form requirement N/A bu modülde).

## Boundary contract

**B-group module:** `modules/agenda` `_MODULES_REQUIRING_LAZY_INIT` listesinde DEĞİL (test_module_init_lazy.py:45-54 — A-group fixed 8 modül). T8-6 LAZY+`_purge_cached_modules` incompatibility ders does **NOT apply**.

**Mevcut 16 import-linter contract:** Yeni contract eklenmedi. Yeni `ignore_imports` eklenmedi.

**0 core/ ORM consumer:** Pre-PR audit (T8-10) `git grep "from app.models.agenda|from app.models import .*AgendaCard" apps/api/app/core` → 0 hits. v77 hard kuralı uyum.

## Veri güvenliği invariant (kullanıcı kuralı)

- `agenda_cards` tablosuna dokunulmadı (file move only, no DDL)
- `Vector(1024)` embedding kolonu Phase 8.2-11'de hardened — re-verify Wave D'de (T8-18 deferred)
- `INSERT/UPDATE/UPSERT agenda_cards` SQL string'leri callerlar'da AYNEN (T8-10 yalnız `from` path değiştirir, statement body değişmez)
- Manual trigger yok; rechunk/reembed/backfill yok

## References

- Master plan: [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.4
- Mini-plan: [`wiki/topics/t8-model-relocation-mini-plan.md`](../../../../wiki/topics/t8-model-relocation-mini-plan.md) (T8-10 / Wave D)
- Boundary: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)

## Migration history

- 2026-05-28: **T8-10** — `AgendaCard` ORM modeli `app/models/agenda.py`'den
  `models.py`'e taşındı (100% rename, 173 satır, git history preserved).
  Modül scaffold (`__init__.py` + `README.md`) bu PR'da oluşturuldu (NEW
  module package). 3 caller flip: `api/admin_queue.py:46` (admin observation)
  + `modules/generations/tasks/agenda.py:31` (Celery task — agenda card
  generator) + `modules/rag/tasks/raptor.py:29` (Celery task — weekly
  summary uses AgendaCard for hierarchical RAPTOR clustering). Wave D ısınma
  (v78 Option B FAIL sonrası T8 risk-classified mode altında 3. başarılı
  safe candidate; T8-8 event, T8-9 research_cluster sonrası). Pre-PR audit
  SAFE: 0 core/ consumer, 0 shared/ consumer, B-group lazy. Behavior-preserving:
  no migration write, no DB schema change, veri güvenliği invariant korunur
  (`agenda_cards` tablosuna dokunulmadı; Vector(1024) embedding Phase 8.2-11
  hardened; relationship() YOK — sadece FK column'ları).
- 2026-05-28: **NEW module scaffold** — Phase 1 retroactive
  (`__init__.py` lazy + `README.md`). T8-10 ile aktif kullanıma alındı.
