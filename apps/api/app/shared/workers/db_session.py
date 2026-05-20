"""Celery worker DB session helpers (Phase 3 PR 1a — extracted from
`app/workers/tasks/sources.py`).

**SCOPE:** Bu helpers source domain'e AİT DEĞİLDİR. Celery sync worker
context'inde async SQLAlchemy session yönetimi için **shared utility**.
Phase 2 sonrası 9 modülün ortak kullandığı düşük-seviye altyapı.

**WHY HERE (shared/workers/, not shared/db/):**
- `shared/db/` genel DB/session altyapısı (FastAPI request scope, engine
  pool, ORM session — async-native)
- `shared/workers/db_session.py` Celery sync task → async DB bridge'i:
  - Her Celery task fresh event loop kullanır (asyncio.run)
  - Async session/engine'ler event-loop-bound; sync worker'da stale olur
    (#109 — "Event loop is closed" hatası)
  - Bu yüzden her task için **fresh engine + dispose** pattern'i gerekir
  - Bu pattern FastAPI request scope'ta gereksiz; sadece Celery worker context

**Public surface (minimal — name değişimi ileride ayrı PR):**
- `_get_session_factory()` — fresh async_sessionmaker (engine pool small)
- `open_session()` — async context manager (engine auto-dispose)
- `_run_async(coro)` — `asyncio.run` wrapper (sync Celery task → async DB)

**Caller usage pattern:**
```python
from app.shared.workers.db_session import _run_async, open_session

@celery_app.task(name="tasks.foo.bar")
def my_task():
    async def run():
        async with open_session() as db:
            ... # SQL operations
    return _run_async(run())
```

**Future cleanup (out of scope for this PR):**
- Public API ismi (private prefix kaldırma) ayrı PR olabilir
- `_get_session_factory` private kalır (caller'lar `open_session`
  context manager'ı tercih etmeli)
- Phase 4+ olası alternatif: native async Celery executor (gerekirse)

History:
- Originally `app/workers/tasks/sources.py:39-88` (lines 39-60, 66-83, 86-88)
- Phase 3 PR 1a (#1126?) — extracted to shared/workers/db_session.py
- Behavior preserved 1-to-1; only path changed

See:
- docs/engineering/modular-monolith-architecture.md §3 (shared layer)
- wiki/decisions/modular-monolith-boundary.md
- wiki/plans/modular-monolith-transition-master-plan.md §13 (status)
- Incident #109 — Celery + asyncpg event loop bug (engine dispose required)
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Her task çağrısı için fresh engine + factory.

    NEDEN PROCESS-WIDE CACHE YOK: Celery sync worker'ı her task için
    ayrı `asyncio.run()` çağırıyor → her seferinde yeni event loop.
    Eski loop'un asyncpg connection'ları stale olur ('Event loop is
    closed' hatası, #109).

    Caller `async with open_session() as db: ...` pattern'ini kullanmalı —
    engine dispose otomatik yapılır.
    """
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
        pool_recycle=300,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    factory._engine = engine  # type: ignore[attr-defined]  # dispose için
    return factory


@asynccontextmanager
async def open_session():
    """Async DB session — fresh engine + auto-dispose.

    Celery + asyncpg event loop bug'a karşı koruma (#109).
    Her task için fresh engine; çıkışta dispose.
    """
    factory = _get_session_factory()
    try:
        async with factory() as session:
            yield session
    finally:
        engine = getattr(factory, "_engine", None)
        if engine is not None:
            try:  # noqa: SIM105
                await engine.dispose()
            except Exception:  # pragma: no cover  # noqa: S110
                pass


def _run_async(coro):
    """Sync Celery task içinden async DB akışını çalıştır."""
    return asyncio.run(coro)


__all__ = ["_get_session_factory", "_run_async", "open_session"]
