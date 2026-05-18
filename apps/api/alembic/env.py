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


def run_migrations_offline() -> None:
    """Offline migration — DB'siz, SQL çıktı verir."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Sync helper — async context içinden çağrılır."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
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
