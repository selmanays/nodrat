"""Alembic env — async-friendly setup.

Settings'ten DB URL'i alır, async engine oluşturur, migrations çalıştırır.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Bu config object Alembic'in geçtiği context.
config = context.config

# Logging setup
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_database_url() -> str:
    """Env'den DB URL'i al.

    pydantic-settings'i import etmek yerine direkt env okuyoruz çünkü
    alembic CLI minimal bağımlılıklarla çalışmalı.
    """
    import os

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL env değişkeni gerekli. .env dosyasını yükleyin veya export edin."
        )
    return url


# target_metadata: tüm modelleri import etmek + Base.metadata vermek
from app.core.db import Base  # noqa: E402
from app.models import *  # noqa: E402, F403  # tüm modelleri register et

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Raw-SQL only tables — autogenerate exclude allowlist (Phase 8 PR-8b-1.5)
# ---------------------------------------------------------------------------
# Autogenerate exclude allowlist consumed by `alembic check` (autogenerate
# diff=0 strict gate), which is ACTIVE in CI (`alembic-check` job in
# .github/workflows/ci.yml runs `alembic check`). Phase 8.2 (#1288, closed
# 2026-05-24) resolved the ORM drift (53 baseline items) and enabled the
# strict gate — T8 ön-şart 5 GREEN.
#
# These 4 tables are raw-SQL only (NO ORM model in app/models/) and are
# excluded here so `alembic check` does not flag them as spurious
# `remove_table` drift. Adding ORM stubs for them is the deferred Phase 8.3
# follow-up; until then they stay on this allowlist.
#
# This filter remains in place for two reasons:
#   1. It is correct: raw-SQL only tables MUST be excluded from autogenerate.
#   2. It documents the 4-table gap explicitly so future ORM-model PRs know
#      which tables to add models for (and remove from this allowlist).
#
# These tables exist in the DB (created by migrations) but have NO ORM model
# in app/models/. Hand-rolled raw SQL access patterns (chunker, retrieval,
# entities pipeline, embedding workers) consume them directly.
#
# Source pointers (where the raw SQL lives):
#   article_chunks         apps/api/app/core/chunker.py + core/retrieval.py
#                          (retrieval.py comments: "hidden in raw SQL since
#                          article_chunks ORM model not defined yet")
#   chat_cache_telemetry   migration 20260518_0200_chat_cache_telemetry
#                          (telemetry-only; no consumer reads ORM mapping)
#   entities               apps/api/app/modules/entities/tasks/entities.py
#                          (NER pipeline; raw SQL upserts by article_id)
#   pmf_survey_responses   no app consumer yet (manual SQL inserts)
RAW_SQL_ONLY_TABLES: frozenset[str] = frozenset(
    {
        "article_chunks",
        "canonical_entities",  # #1540 entity canonicalization (raw-SQL, entities deseni)
        "chat_cache_telemetry",
        "entities",
        "entity_aliases",  # #1540 entity canonicalization
        "pmf_survey_responses",
        "user_notifications",  # #1581 trend-alert bildirimleri (raw-SQL, canonical deseni)
        "wikidata_entity_resolutions",  # #1710 Wikidata canonical-etiket guard/cache (raw-SQL)
    }
)


def _include_object(object_, name, type_, reflected, compare_to):
    """Exclude raw-SQL only tables (and their indexes/FKs) from autogenerate.

    Used by `alembic check` (ACTIVE in CI — autogenerate diff=0 strict gate)
    to compute schema drift between SQLAlchemy models and the migrated DB.
    Without the filter, raw-SQL tables surface as spurious `remove_table`
    suggestions.

    Wired into `context.configure()` so both the CI `alembic check` gate and
    manual `alembic revision --autogenerate` honor the exclusion.
    """
    if type_ == "table" and name in RAW_SQL_ONLY_TABLES:
        return False
    if type_ in ("index", "unique_constraint", "foreign_key", "check_constraint"):
        parent_table = getattr(object_, "table", None)
        if parent_table is not None and parent_table.name in RAW_SQL_ONLY_TABLES:
            return False
    return True


def run_migrations_offline() -> None:
    """Offline migration — DB'siz, SQL çıktı verir."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Sync helper — async context içinden çağrılır."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Async migration runner."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Online migration — gerçek DB connection ile."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
