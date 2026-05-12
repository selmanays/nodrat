"""Integration tests for admin RAG endpoints — SQL syntax doğrulama (#227).

#227 hotfix: rerank-stats endpoint'i `:hours || ' hours'::interval` SQL'inde
asyncpg int+string concat hatası veriyordu. make_interval() ile fix edildi.
Bu test SQL'in production-benzeri DB'de gerçekten çalıştığını doğrular.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_rerank_stats_sql_int_param_no_data_error(test_db_session):
    """make_interval() ile int param → DataError olmaz, SQL çalışır.

    Eski hatalı SQL: `(:hours || ' hours')::interval` → asyncpg DataError.
    Yeni: `make_interval(hours => :hours)` → ✓
    """
    # Tablo yoksa hata almayalım — varsa filter çalışsın.
    # #758: nim_rerank kaldırıldı; SQL pattern test için 'deepseek' yeterli.
    try:
        result = await test_db_session.execute(
            text(
                """
                SELECT COUNT(*) AS c
                FROM provider_call_logs
                WHERE provider = 'deepseek'
                  AND created_at > NOW() - make_interval(hours => :hours)
                """
            ),
            {"hours": 24},
        )
        # Sonuç 0 da olabilir, önemli olan SQL hatasız çalışsın
        row = result.scalar()
        assert isinstance(row, int)
    except Exception as exc:
        if "provider_call_logs" in str(exc).lower():
            pytest.skip("provider_call_logs tablosu test DB'sinde yok")
        raise


@pytest.mark.asyncio
async def test_rerank_stats_sql_various_hour_values(test_db_session):
    """1, 24, 168 saatlik aralıklar — hepsi int olarak geçirilebilmeli."""
    try:
        for hours in (1, 24, 168):
            await test_db_session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM provider_call_logs
                    WHERE created_at > NOW() - make_interval(hours => :hours)
                    """
                ),
                {"hours": hours},
            )
    except Exception as exc:
        if "provider_call_logs" in str(exc).lower():
            pytest.skip("provider_call_logs tablosu test DB'sinde yok")
        raise
