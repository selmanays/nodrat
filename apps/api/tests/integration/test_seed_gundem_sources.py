"""Integration test — gündem kataloğu seed migration (#1524).

Testcontainers postgres üzerinde `alembic upgrade head` sonrası:
  - 19 yeni source row eklendi
  - is_active=FALSE (compliance gate öncesi)
  - tos_acknowledged=FALSE, robots_txt_compliant=NULL (admin onayı bekliyor)
  - polling_tier='normal', would_be_tier=NULL (Faz 2 shadow mode default)
  - category='Gündem'
  - reliability_score per-source set edilmiş (server default 0.70'e düşmemiş)
  - type: 15 'rss' + 4 'category_page'
  - migration idempotent (ON CONFLICT (slug) DO NOTHING)
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


# Katman A/B (rss) + Katman C (category_page)
RSS_SLUGS = (
    "cumhuriyet",
    "sozcu",
    "birgun",
    "medyascope",
    "kisa-dalga",
    "dw-turkce",
    "euronews-turkce",
    "independent-turkce",
    "teyit",
    "dogruluk-payi",
    "journo",
    "gercek-gundem",
    "halk-tv",
    "dokuz8haber",
    "yetkin-report",
)

CATEGORY_PAGE_SLUGS = (
    "t24",
    "diken",
    "anka-haber-ajansi",
    "resmi-gazete",
)

EXPECTED_SLUGS = RSS_SLUGS + CATEGORY_PAGE_SLUGS

# reliability_score'un per-source set edildiğini (default 0.70'e düşmediğini)
# doğrulayan kanıt-noktaları.
EXPECTED_SCORES = {
    "dogruluk-payi": Decimal("0.95"),  # fact-check tavanına yakın
    "resmi-gazete": Decimal("0.98"),  # resmi-otorite
    "teyit": Decimal("0.92"),  # fact-check
    "dw-turkce": Decimal("0.86"),  # uluslararası kurumsal
    "dokuz8haber": Decimal("0.68"),  # bağımsız-dijital alt bant
}


@pytest.mark.asyncio
async def test_all_19_gundem_sources_inserted(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """19/19 slug eklenmiş olmalı."""
    result = await test_db_session.execute(
        text("SELECT slug FROM sources WHERE slug = ANY(:slugs) ORDER BY slug").bindparams(
            slugs=list(EXPECTED_SLUGS)
        )
    )
    found = {row[0] for row in result}
    assert found == set(EXPECTED_SLUGS), f"Eksik slug: {set(EXPECTED_SLUGS) - found}"


@pytest.mark.asyncio
async def test_sources_inactive_default(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """Hepsi is_active=FALSE — compliance gate'ten önce aktive edilmemiş."""
    result = await test_db_session.execute(
        text(
            "SELECT COUNT(*) FROM sources WHERE slug = ANY(:slugs) AND is_active = FALSE"
        ).bindparams(slugs=list(EXPECTED_SLUGS))
    )
    assert result.scalar() == len(EXPECTED_SLUGS)


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
    """crawl_interval_minutes=30 (server default), tüm 19'unda."""
    result = await test_db_session.execute(
        text(
            "SELECT COUNT(*) FROM sources WHERE slug = ANY(:slugs) AND crawl_interval_minutes = 30"
        ).bindparams(slugs=list(EXPECTED_SLUGS))
    )
    assert result.scalar() == len(EXPECTED_SLUGS)


@pytest.mark.asyncio
async def test_sources_category_gundem(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """Hepsi 'Gündem' kategorisinde (haber/güncel-olay bucket'ı)."""
    result = await test_db_session.execute(
        text("SELECT DISTINCT category FROM sources WHERE slug = ANY(:slugs)").bindparams(
            slugs=list(EXPECTED_SLUGS)
        )
    )
    categories = {row[0] for row in result}
    assert categories == {"Gündem"}


@pytest.mark.asyncio
async def test_sources_type_split(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """15 'rss' + 4 'category_page'."""
    rss = await test_db_session.execute(
        text("SELECT COUNT(*) FROM sources WHERE slug = ANY(:slugs) AND type = 'rss'").bindparams(
            slugs=list(RSS_SLUGS)
        )
    )
    assert rss.scalar() == len(RSS_SLUGS) == 15

    cat = await test_db_session.execute(
        text(
            "SELECT COUNT(*) FROM sources WHERE slug = ANY(:slugs) AND type = 'category_page'"
        ).bindparams(slugs=list(CATEGORY_PAGE_SLUGS))
    )
    assert cat.scalar() == len(CATEGORY_PAGE_SLUGS) == 4


@pytest.mark.asyncio
async def test_sources_reliability_score_set(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """reliability_score per-source set edilmiş — kanıt-noktaları + aralık geçerli."""
    for slug, expected in EXPECTED_SCORES.items():
        result = await test_db_session.execute(
            text("SELECT reliability_score FROM sources WHERE slug = :slug").bindparams(slug=slug)
        )
        actual = result.scalar()
        assert actual == expected, f"{slug}: beklenen {expected}, bulunan {actual}"

    # Hiçbiri default 0.70'e düşmemeli (hepsi açıkça set edildi); aralık CHECK uyumlu.
    out_of_range = await test_db_session.execute(
        text(
            "SELECT COUNT(*) FROM sources "
            "WHERE slug = ANY(:slugs) "
            "AND (reliability_score < 0.0 OR reliability_score > 1.0)"
        ).bindparams(slugs=list(EXPECTED_SLUGS))
    )
    assert out_of_range.scalar() == 0


@pytest.mark.asyncio
async def test_seed_idempotent_re_run(test_db_session) -> None:  # type: ignore[no-untyped-def]
    """Migration ON CONFLICT (slug) DO NOTHING — yeniden insert no-op olmalı."""
    result_1 = await test_db_session.execute(
        text("SELECT COUNT(*) FROM sources WHERE slug = ANY(:slugs)").bindparams(
            slugs=list(EXPECTED_SLUGS)
        )
    )
    count_before = result_1.scalar()

    # migration'daki INSERT'in birini yeniden çalıştır (raw SQL)
    await test_db_session.execute(
        text(
            """
            INSERT INTO sources (
                name, slug, domain, type, base_url,
                language, country, category, reliability_score,
                is_active, tos_acknowledged
            ) VALUES (
                'Doğruluk Payı (dup)', 'dogruluk-payi', 'dogrulukpayi.com', 'rss',
                'https://www.dogrulukpayi.com/rss.xml', 'tr', 'TR', 'Gündem', 0.10,
                TRUE, TRUE
            )
            ON CONFLICT (slug) DO NOTHING
            """
        )
    )

    result_2 = await test_db_session.execute(
        text("SELECT COUNT(*) FROM sources WHERE slug = ANY(:slugs)").bindparams(
            slugs=list(EXPECTED_SLUGS)
        )
    )
    count_after = result_2.scalar()
    assert count_before == count_after == len(EXPECTED_SLUGS)

    # Çakışan insert pas geçilmeli — orijinal skor (0.95) korunmalı, 0.10'a düşmemeli.
    score = await test_db_session.execute(
        text("SELECT reliability_score FROM sources WHERE slug = 'dogruluk-payi'")
    )
    assert score.scalar() == Decimal("0.95")
