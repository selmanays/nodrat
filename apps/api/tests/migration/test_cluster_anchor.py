"""Integration — #1590 küme çapası canonical-aware + tip-filtre (testcontainers).

`_ENTITY_DF_SQL` (cluster_assigner): query-gram'ları entities ile eşler, alias→
canonical map (COALESCE) + person/org/place/event tip-filtresi. "trump"/"donald trump"
→ tek canonical "donald trump" (display "Donald Trump"); "bir"(number) elenir.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.generations.tasks.cluster_assigner import _ENTITY_DF_SQL
from sqlalchemy import text

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


async def _src(db) -> uuid.UUID:
    sid = uuid.uuid4()
    slug = f"s-{sid.hex[:8]}"
    await db.execute(
        text(
            "INSERT INTO sources (id, name, slug, domain, type, base_url, reliability_score) "
            "VALUES (:id, :n, :s, :d, 'rss', :u, 0.8)"
        ),
        {"id": sid, "n": slug, "s": slug, "d": f"{slug}.x", "u": f"https://{slug}.x"},
    )
    return sid


async def _ent(db, sid: uuid.UUID, norm: str, etype: str, n: int) -> None:
    for i in range(n):
        aid = uuid.uuid4()
        h = aid.hex
        await db.execute(
            text(
                "INSERT INTO articles (id, source_id, canonical_url, source_url, title, "
                "content_hash, title_hash, published_at) VALUES (:id,:s,:u,:u,'t',:h,:h,:p)"
            ),
            {"id": aid, "s": sid, "u": f"https://x/{h}", "h": h, "p": _NOW - timedelta(hours=i)},
        )
        await db.execute(
            text(
                "INSERT INTO entities (article_id, entity_text, entity_normalized, entity_type) "
                "VALUES (:a,:t,:n,:et)"
            ),
            {"a": aid, "t": norm, "n": norm, "et": etype},
        )


async def test_anchor_query_canonical_map_and_type_filter(test_db_session):
    db = test_db_session
    s = await _src(db)
    await _ent(db, s, "trump", "person", 5)  # kısa form
    await _ent(db, s, "donald trump", "person", 12)  # tam form
    await _ent(db, s, "bir", "number", 3)  # gürültü (tip-filtre eler)

    # canonical "Donald Trump" + alias map (trump + donald trump)
    cid = (
        await db.execute(
            text(
                "INSERT INTO canonical_entities (canonical_name, entity_type, canonical_normalized, "
                "source) VALUES ('Donald Trump','person','donald trump','seed') RETURNING id"
            )
        )
    ).scalar()
    for a in ("trump", "donald trump"):
        await db.execute(
            text(
                "INSERT INTO entity_aliases (alias_normalized, entity_type, canonical_id, "
                "confidence, source) VALUES (:a,'person',:c,1.000,'seed')"
            ),
            {"a": a, "c": cid},
        )

    rows = (await db.execute(_ENTITY_DF_SQL, {"grams": ["trump", "donald trump", "bir"]})).all()
    by_norm = {r.norm: r for r in rows}

    # "bir" (number) → tip-filtre eledi
    assert "bir" not in by_norm
    # trump + donald trump → tek canonical "donald trump" (display "Donald Trump")
    assert "donald trump" in by_norm
    assert "trump" not in by_norm  # ayrı kalmadı, canonical'a maplendi
    row = by_norm["donald trump"]
    assert row.etype == "person"
    assert row.has_canonical is True
    assert row.display_name == "Donald Trump"
    assert int(row.df) == 17  # 5 + 12 birleşti
