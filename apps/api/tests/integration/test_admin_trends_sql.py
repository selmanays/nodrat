"""Integration — admin Trend Overview SQL + endpoint ON-path (#1500).

Faz 1 trend SQL'inin production-benzeri DB'de (asyncpg) gerçekten çalıştığını
doğrular — özellikle #227-tipi asyncpg param/interval hatalarına karşı koruma.
Endpoint ON-path'i boş DB'de uçtan uca koşar (serileştirme + tüm SQL).

testcontainers gerektirir → Docker yoksa otomatik skip (conftest gating).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import bindparam, text

pytestmark = pytest.mark.integration


_PARAMS = {
    # production endpoint'iyle aynı param tipleri (datetime + int)
    "win_start": "2026-06-14 00:00:00+00",
    "prev_start": "2026-06-13 00:00:00+00",
    "now_ts": "2026-06-15 00:00:00+00",
}


async def test_total_count_sql_runs(test_db_session):
    """DISTINCT event_id sayımı asyncpg'de hatasız çalışır (boş = 0)."""
    row = await test_db_session.execute(
        text(
            """
            SELECT COUNT(DISTINCT ea.event_id) AS total
            FROM event_articles ea
            WHERE ea.published_at >= :prev_start AND ea.published_at < :now_ts
            """
        ),
        _PARAMS,
    )
    assert isinstance(row.scalar(), int)


async def test_main_aggregation_sql_runs(test_db_session):
    """Koşullu FILTER agregasyonu + subquery momentum ORDER BY (alias-in-expr) hatasız.

    Production admin_trends.py ile aynı subquery yapısı: ORDER BY dış sorguda →
    momentum ifadesi cur_count/prev_count alias'larını gerçek kolon olarak görür.
    Düz (subquery'siz) ORDER BY içinde alias → PG 'column does not exist' verir.
    """
    result = await test_db_session.execute(
        text(
            """
            SELECT * FROM (
                SELECT
                    ec.id AS cluster_id,
                    COUNT(*) FILTER (
                        WHERE ea.published_at >= :win_start AND ea.published_at < :now_ts
                    ) AS cur_count,
                    COUNT(*) FILTER (
                        WHERE ea.published_at >= :prev_start AND ea.published_at < :win_start
                    ) AS prev_count,
                    COUNT(DISTINCT ea.source_id) FILTER (
                        WHERE ea.published_at >= :win_start AND ea.published_at < :now_ts
                    ) AS unique_sources,
                    AVG(s.reliability_score) FILTER (
                        WHERE ea.published_at >= :win_start AND ea.published_at < :now_ts
                    ) AS avg_reliability
                FROM event_articles ea
                JOIN event_clusters ec ON ec.id = ea.event_id
                LEFT JOIN sources s ON s.id = ea.source_id
                WHERE ea.published_at >= :prev_start AND ea.published_at < :now_ts
                GROUP BY ec.id
            ) AS agg_t
            ORDER BY (cur_count - prev_count)::float / NULLIF(prev_count, 0)
                     DESC NULLS FIRST, cur_count DESC
            LIMIT 50 OFFSET 0
            """
        ),
        _PARAMS,
    )
    assert result.all() == []  # boş DB


async def test_sparkline_expanding_in_sql_runs(test_db_session):
    """floor(epoch/bucket) bucketing + expanding UUID IN (asyncpg riski) hatasız."""
    spark_sql = text(
        """
        SELECT ea.event_id AS cluster_id,
               floor(
                   extract(epoch FROM (ea.published_at - :win_start)) / :bucket_sec
               )::int AS bucket_idx,
               COUNT(*) AS cnt
        FROM event_articles ea
        WHERE ea.event_id IN :ids
          AND ea.published_at >= :win_start AND ea.published_at < :now_ts
        GROUP BY ea.event_id, bucket_idx
        """
    ).bindparams(bindparam("ids", expanding=True))
    result = await test_db_session.execute(
        spark_sql,
        {
            "win_start": _PARAMS["win_start"],
            "now_ts": _PARAMS["now_ts"],
            "bucket_sec": 7200,
            "ids": [uuid4(), uuid4()],
        },
    )
    assert result.all() == []


async def test_endpoint_on_path_empty_db(test_db_session, monkeypatch):
    """Flag ON + boş DB → enabled=True, data=[], total=0; tüm SQL uçtan uca koşar."""
    import app.api.admin_trends as mod

    class _Store:
        async def get(self, db, key, default=None):
            return "24h" if key == "trends.overview.window_default" else default

        async def get_bool(self, db, key, default):
            return True if key == "trends.enabled" else default

    monkeypatch.setattr(mod, "settings_store", _Store())
    resp = await mod.list_trends(
        admin=object(),
        db=test_db_session,
        window="24h",
        sort="momentum",
        limit=50,
        offset=0,
    )
    assert resp.enabled is True
    assert resp.data == []
    assert resp.total == 0
    assert resp.window == "24h"
