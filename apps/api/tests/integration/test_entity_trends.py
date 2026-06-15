"""Integration — entity-merkezli trend okuma (#1518, Docker-gated).

_read_entity_trends: `entities ⋈ articles` agregasyonu + evidence gate (≥2 haber
& ≥2 kaynak) + birleşik skor. Gate'i geçen entity, label = entity adı (ham başlık
DEĞİL) ile döner; tek-haber entity ana listeden elenir; gate kapalıyken görünür.

testcontainers gerektirir → Docker yoksa otomatik skip (conftest gating).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.api.admin_trends import _read_entity_trends
from sqlalchemy import text

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
_WIN_START = _NOW - timedelta(hours=24)
_PREV_START = _NOW - timedelta(hours=48)


async def _seed_source(db, name: str, reliability: float) -> uuid.UUID:
    sid = uuid.uuid4()
    slug = f"src-{sid.hex[:8]}"
    await db.execute(
        text(
            "INSERT INTO sources (id, name, slug, domain, type, base_url, "
            "reliability_score) VALUES (:id, :n, :slug, :dom, 'rss', :url, :rel)"
        ),
        {
            "id": sid,
            "n": name,
            "slug": slug,
            "dom": f"{slug}.example",
            "url": f"https://{slug}.example",
            "rel": reliability,
        },
    )
    return sid


async def _seed_article(db, sid: uuid.UUID, pub: datetime) -> uuid.UUID:
    aid = uuid.uuid4()
    h = aid.hex
    await db.execute(
        text(
            "INSERT INTO articles (id, source_id, canonical_url, source_url, title, "
            "content_hash, title_hash, published_at) "
            "VALUES (:id, :sid, :u, :u, 'Test Haber', :h, :h, :pub)"
        ),
        {"id": aid, "sid": sid, "u": f"https://x/{h}", "h": h, "pub": pub},
    )
    return aid


async def _seed_entity(db, aid: uuid.UUID, text_form: str, norm: str, etype: str) -> None:
    await db.execute(
        text(
            "INSERT INTO entities (article_id, entity_text, entity_normalized, "
            "entity_type) VALUES (:a, :t, :n, :et)"
        ),
        {"a": aid, "t": text_form, "n": norm, "et": etype},
    )


async def test_entity_trend_gate_label_and_score(test_db_session):
    db = test_db_session
    s1 = await _seed_source(db, "Kaynak A", 0.8)
    s2 = await _seed_source(db, "Kaynak B", 0.6)

    # Trending entity: 3 haber / 2 kaynak (gate ≥2/≥2 geçer)
    norm = f"test-entity-{uuid.uuid4().hex[:6]}"
    for sid, hours in [(s1, 1), (s1, 2), (s2, 3)]:
        aid = await _seed_article(db, sid, _NOW - timedelta(hours=hours))
        await _seed_entity(db, aid, "Test Entity", norm, "org")

    # Noise entity: 1 haber / 1 kaynak (gate altı)
    noise = f"noise-{uuid.uuid4().hex[:6]}"
    aid = await _seed_article(db, s1, _NOW - timedelta(hours=1))
    await _seed_entity(db, aid, "Noise", noise, "person")

    data, _total = await _read_entity_trends(
        db, _WIN_START, _PREV_START, _NOW, "score", 12, 7200, 50, 0, 2, 2
    )
    by_id = {d.cluster_id: d for d in data}

    assert f"org:{norm}" in by_id  # gate geçti
    item = by_id[f"org:{norm}"]
    assert item.title == "Test Entity"  # label = entity adı, ham başlık değil
    assert item.entity_type == "org"
    assert item.article_count == 3
    assert item.unique_source_count == 2
    assert item.trend_score is not None and 0.0 < item.trend_score <= 1.0
    # 3 haber + baseline yok → breaking (compute_trend_state cur>=3)
    assert item.trend_state == "breaking"

    assert f"person:{noise}" not in by_id  # tek-haber gate altı → elendi

    # gate kapalı (0/0) → noise da görünür (reversible)
    data_open, _ = await _read_entity_trends(
        db, _WIN_START, _PREV_START, _NOW, "score", 12, 7200, 50, 0, 0, 0
    )
    assert any(d.cluster_id == f"person:{noise}" for d in data_open)


async def test_entity_trend_empty_db(test_db_session):
    """Entity yok → boş liste, total 0 (no-op, asyncpg SQL hatasız)."""
    data, total = await _read_entity_trends(
        test_db_session, _WIN_START, _PREV_START, _NOW, "score", 12, 7200, 50, 0, 2, 2
    )
    assert data == []
    assert total == 0
