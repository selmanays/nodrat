"""Phase 8 PR-8b-2 — Fresh upgrade test.

Pytest-runnable version of the CI `alembic-check` job's `alembic upgrade head`
step (PR-8b-1 #1251). Confirms that:

1. A fresh disposable Postgres+pgvector DB can apply the full migration chain
   without error.
2. The `vector` extension is loaded (init_extensions migration ran).
3. Exactly one alembic head exists post-upgrade (no accidental branching).
4. A few well-known tables exist after upgrade (sanity check that
   `target_metadata` was honored and ORM-registered models created their
   tables — catches regression of the 3-model __init__ omission fixed in
   PR-8b-1).

The CI job is the primary gate (always runs); this pytest version gives
developers a fast local-runnable check during alembic-touching work.

Marker: `integration` — auto-skipped if docker daemon is unavailable
(see tests/conftest.py::pytest_collection_modifyitems).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.mark.integration
async def test_alembic_upgrade_head_to_fresh_db(test_db_engine):
    """`alembic upgrade head` succeeds on a fresh disposable DB.

    The `test_db_engine` session-scoped fixture runs `alembic upgrade head`
    during setup; if we got here, upgrade succeeded. We then perform a basic
    sanity sweep — a handful of well-known production tables must exist.
    """
    expected_tables = ("users", "articles", "sources", "messages", "conversations")
    async with test_db_engine.connect() as conn:
        for name in expected_tables:
            result = await conn.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = :name"
                    ")"
                ),
                {"name": name},
            )
            assert result.scalar() is True, f"Table {name!r} missing after upgrade head"


@pytest.mark.integration
async def test_pgvector_extension_loaded(test_db_engine):
    """`vector` extension is enabled (proves init_extensions migration ran).

    Required by `article_chunks.embedding`, `agenda_cards.embedding`, etc.
    A bare `postgres:16` image would fail here — pgvector/pgvector:pg16 is
    needed (see PR-8b-1 #1251 followup).
    """
    async with test_db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        )
        assert result.scalar() is True, "`vector` extension not loaded post-upgrade"


@pytest.mark.integration
async def test_alembic_head_single(test_db_engine):
    """Exactly one alembic version is current — no accidental branching.

    `alembic_version` table holds the applied head(s). For a linear migration
    chain there must be exactly one row.
    """
    async with test_db_engine.connect() as conn:
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        rows = result.fetchall()
    assert len(rows) == 1, f"Expected exactly one alembic head, found {len(rows)}: {rows}"
