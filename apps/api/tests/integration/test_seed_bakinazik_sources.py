"""Integration test — bakinazik kataloğu seed migration (#585).

Testcontainers postgres üzerinde `alembic upgrade head` sonrası:
  - 20 yeni source row eklendi
  - is_active=FALSE (compliance gate öncesi)
  - polling_tier='normal' (Faz 2 shadow mode default)
  - would_be_tier=NULL (ilk fetch'te dolacak)
  - category alanı bakinazik etiketi
  - 10 farklı kategori temsili
  - migration idempotent (yeniden çalıştırıldığında satır sayısı sabit)
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


EXPECTED_SLUGS = (
    "evrim-agaci",
    "sarkac",
    "webtekno",
    "donanim-haber",
    "beyaz-perde",
    "ign-turkiye",
    "arkitera",
    "bant-mag",
    "ntv-spor",
    "fotomac",
    "bianet",
    "hurriyet",
    "c4-defence",
    "savunma-sanayi-st",
    "bloomberg-ht",
    "forbes-turkiye",
    "midas",
    "isin-detayi-is-dunyasi",
    "elle-turkiye",
    "marie-claire",
)

EXPECTED_CATEGORIES = {
    "Bilim",
    "Teknoloji",
    "Eğlence",
    "Kültür ve Sanat",
    "Spor",
    "Gündem",
    "Savunma ve Sanayi",
    "Ekonomi ve Finans",
    "İş Dünyası",
    "Yaşam",
}


@pytest.mark.asyncio
async def test_all_20_bakinazik_sources_inserted(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """20/20 slug eklenmiş olmalı."""
    result = await test_db_session.execute(
        text(
            "SELECT slug FROM sources WHERE slug = ANY(:slugs) ORDER BY slug"
        ).bindparams(slugs=list(EXPECTED_SLUGS))
    )
    found = {row[0] for row in result}
    assert found == set(EXPECTED_SLUGS), f"Eksik slug: {set(EXPECTED_SLUGS) - found}"


@pytest.mark.asyncio
async def test_sources_inactive_default(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """Hepsi is_active=FALSE — compliance gate'ten önce aktive edilmemiş."""
    result = await test_db_session.execute(
        text(
            "SELECT COUNT(*) FROM sources "
            "WHERE slug = ANY(:slugs) AND is_active = FALSE"
        ).bindparams(slugs=list(EXPECTED_SLUGS))
    )
    assert result.scalar() == len(EXPECTED_SLUGS)


@pytest.mark.asyncio
async def test_sources_polling_tier_normal_default(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """Faz 2 shadow mode uyum: polling_tier='normal', would_be_tier=NULL."""
    result = await test_db_session.execute(
        text(
            "SELECT COUNT(*) FROM sources "
            "WHERE slug = ANY(:slugs) "
            "AND polling_tier = 'normal' "
            "AND would_be_tier IS NULL "
            "AND tier_metadata IS NULL"
        ).bindparams(slugs=list(EXPECTED_SLUGS))
    )
    assert result.scalar() == len(EXPECTED_SLUGS)


@pytest.mark.asyncio
async def test_sources_crawl_interval_default(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """crawl_interval_minutes=30 (server default), tüm 20'sinde."""
    result = await test_db_session.execute(
        text(
            "SELECT COUNT(*) FROM sources "
            "WHERE slug = ANY(:slugs) AND crawl_interval_minutes = 30"
        ).bindparams(slugs=list(EXPECTED_SLUGS))
    )
    assert result.scalar() == len(EXPECTED_SLUGS)


@pytest.mark.asyncio
async def test_sources_all_10_categories_present(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """10 bakinazik kategorisinin hepsi temsil edilmiş."""
    result = await test_db_session.execute(
        text(
            "SELECT DISTINCT category FROM sources WHERE slug = ANY(:slugs)"
        ).bindparams(slugs=list(EXPECTED_SLUGS))
    )
    categories = {row[0] for row in result}
    assert categories == EXPECTED_CATEGORIES


@pytest.mark.asyncio
async def test_sources_compliance_fields_unset(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """tos_acknowledged=FALSE, robots_txt_compliant=NULL — admin onayı bekliyor."""
    result = await test_db_session.execute(
        text(
            "SELECT COUNT(*) FROM sources "
            "WHERE slug = ANY(:slugs) "
            "AND tos_acknowledged = FALSE "
            "AND robots_txt_compliant IS NULL"
        ).bindparams(slugs=list(EXPECTED_SLUGS))
    )
    assert result.scalar() == len(EXPECTED_SLUGS)


@pytest.mark.asyncio
async def test_seed_idempotent_re_run(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """Migration ON CONFLICT (slug) DO NOTHING — yeniden insert no-op olmalı."""
    # 1. ilk count
    result_1 = await test_db_session.execute(
        text("SELECT COUNT(*) FROM sources WHERE slug = ANY(:slugs)").bindparams(
            slugs=list(EXPECTED_SLUGS)
        )
    )
    count_before = result_1.scalar()

    # 2. migration'daki INSERT'in birini yeniden çalıştır (raw SQL)
    await test_db_session.execute(
        text(
            """
            INSERT INTO sources (
                name, slug, domain, type, base_url,
                language, country, category, is_active, tos_acknowledged
            ) VALUES (
                'Evrim Ağacı (dup)', 'evrim-agaci', 'evrimagaci.org', 'rss',
                'https://evrimagaci.org/rss.xml', 'tr', 'TR', 'Bilim',
                FALSE, FALSE
            )
            ON CONFLICT (slug) DO NOTHING
            """
        )
    )

    # 3. count değişmemiş olmalı
    result_2 = await test_db_session.execute(
        text("SELECT COUNT(*) FROM sources WHERE slug = ANY(:slugs)").bindparams(
            slugs=list(EXPECTED_SLUGS)
        )
    )
    count_after = result_2.scalar()

    assert count_before == count_after == len(EXPECTED_SLUGS)


@pytest.mark.asyncio
async def test_seeded_sources_pass_polling_tier_check_constraint(
    test_db_session,  # type: ignore[no-untyped-def]
) -> None:
    """`polling_tier IN ('hot','normal','cold','hibernate')` constraint OK."""
    # Hepsi 'normal' default; constraint zaten valid değer aralığında.
    result = await test_db_session.execute(
        text(
            "SELECT COUNT(*) FROM sources "
            "WHERE slug = ANY(:slugs) "
            "AND polling_tier IN ('hot','normal','cold','hibernate')"
        ).bindparams(slugs=list(EXPECTED_SLUGS))
    )
    assert result.scalar() == len(EXPECTED_SLUGS)
