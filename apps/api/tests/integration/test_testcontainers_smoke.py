"""Testcontainers smoke — fixture'lar ayağa kalkıyor mu?

#43 baseline test. Docker yoksa otomatik skip.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_pg_container_responds(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """test_db_session fixture'i ayağa kalktıysa basit SELECT 1 çalışır."""
    from sqlalchemy import text

    result = await test_db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_pg_has_pgvector_extension(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """Migration sonrası pgvector kurulu olmalı."""
    from sqlalchemy import text

    result = await test_db_session.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    )
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_users_table_exists_after_migration(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """alembic upgrade head sonrası users tablosu var."""
    from sqlalchemy import text

    result = await test_db_session.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='users'"
        )
    )
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_articles_table_exists_after_migration(test_db_session) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    result = await test_db_session.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='articles'"
        )
    )
    assert result.scalar() == 1


def test_redis_url_fixture(redis_url: str) -> None:
    """Redis container ayakta — URL string biçimli."""
    assert redis_url.startswith("redis://")


def test_minio_endpoint_fixture(minio_endpoint: str) -> None:
    """MinIO container ayakta — endpoint host:port."""
    assert ":" in minio_endpoint
