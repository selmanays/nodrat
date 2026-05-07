"""Database session + Base model.

SQLAlchemy 2.0 async pattern.
docs/engineering/architecture.md §3.1, docs/engineering/data-model.md
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Tüm SQLAlchemy modellerin base class'ı."""

    pass


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> Any:
    """Cached async engine.

    #256 — Pool config tuned to avoid TooManyConnectionsError on container
    restart. 7 container × 15 max conn = 105, postgres max_connections=300
    yedeği var. pool_recycle=300 connection leak'i önler (5 dk sonra
    connection kapanır ve tekrar açılır).
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.is_development,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle_seconds,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Cached session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: per-request session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()
