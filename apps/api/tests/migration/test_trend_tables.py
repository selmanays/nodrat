"""Trend tabloları — migration upgrade sonrası varlık + constraint (Faz 2 PR-2a, #1505).

`test_db_engine` fixture `alembic upgrade head` çalıştırır (20260615_1200 dahil).
Bu test 4 trend tablosunun + kritik unique/index'lerin oluştuğunu doğrular.
Docker yoksa otomatik skip (conftest gating). alembic check 0-diff = CI gate.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def _exists(conn, sql, params):
    return (await conn.execute(text(sql), params)).scalar()


async def test_trend_tables_exist(test_db_engine):
    async with test_db_engine.connect() as conn:
        for name in ("topics", "topic_clusters", "trend_snapshots", "trend_signals"):
            ok = await _exists(
                conn,
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:n)",
                {"n": name},
            )
            assert ok is True, f"{name} tablosu yok"


async def test_snapshot_idempotency_unique_constraint(test_db_engine):
    async with test_db_engine.connect() as conn:
        ok = await _exists(
            conn,
            "SELECT EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conname='uq_trend_snapshots_subject_bucket_algo')",
            {},
        )
        assert ok is True


async def test_topics_slug_unique_and_ivfflat_index(test_db_engine):
    async with test_db_engine.connect() as conn:
        uq = await _exists(
            conn,
            "SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_topics_slug')",
            {},
        )
        assert uq is True
        idx = await _exists(
            conn,
            "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname='idx_topics_centroid')",
            {},
        )
        assert idx is True


async def test_signals_dedup_unique_constraint(test_db_engine):
    async with test_db_engine.connect() as conn:
        ok = await _exists(
            conn,
            "SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_trend_signals_dedup')",
            {},
        )
        assert ok is True
