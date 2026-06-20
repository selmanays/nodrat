"""Integration — Faz 3 cluster_resolver + artifact oluşturma servisi (testcontainers).

resolve_cluster_by_entity: sorgu→kanonik entity-küme (senkron, artefakt için).
create_artifact_with_revision: küme-bağlı artefakt + ilk revizyon (seq=1, initial).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.generations.artifacts import create_artifact_with_revision
from app.modules.generations.cluster_resolver import resolve_cluster_by_entity
from sqlalchemy import text

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


async def _user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:id, :e, 'x')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@test.local"},
    )
    return uid


async def _cluster(db) -> uuid.UUID:
    cid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO research_clusters (id, cluster_key, cluster_type, canonical_name) "
            "VALUES (:id, :k, 'topic', 'Test Küme')"
        ),
        {"id": cid, "k": f"topic:{cid.hex[:10]}"},
    )
    return cid


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


async def test_create_artifact_with_revision(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)

    aid = await create_artifact_with_revision(
        db,
        user_id=uid,
        cluster_id=cid,
        content="ilk içerik",
        artifact_type="thread",
        sources_used=[{"title": "x"}],
        effective_query="trump ne dedi",
    )

    art = (
        await db.execute(
            text(
                "SELECT artifact_type, head_revision_id, cluster_id, user_id "
                "FROM artifacts WHERE id=:a"
            ),
            {"a": aid},
        )
    ).one()
    assert art.artifact_type == "thread"
    assert art.cluster_id == cid
    assert art.user_id == uid
    assert art.head_revision_id is not None

    rev = (
        await db.execute(
            text(
                "SELECT id, revision_seq, revision_intent, content "
                "FROM artifact_revisions WHERE artifact_id=:a"
            ),
            {"a": aid},
        )
    ).one()
    assert rev.revision_seq == 1
    assert rev.revision_intent == "initial"
    assert rev.content == "ilk içerik"
    # head_revision ilk revizyonu işaret eder
    assert art.head_revision_id == rev.id


async def test_resolve_cluster_by_entity_creates_and_finds(test_db_session):
    db = test_db_session
    # entity "trump" → 2 kaynak × 1 makale (df=2, src=2 → evidence-gate geçer)
    s1 = await _src(db)
    await _ent(db, s1, "trump", "person", 1)
    s2 = await _src(db)
    await _ent(db, s2, "trump", "person", 1)

    # create=False, küme yok → None
    assert await resolve_cluster_by_entity(db, "trump ne dedi", create=False) is None
    # create=True → kanonik küme oluşur
    c = await resolve_cluster_by_entity(db, "trump ne dedi bugün", create=True)
    assert c is not None
    assert c.cluster_key == "person:trump"
    assert c.cluster_type == "person"
    # tekrar → mevcut bulunur (tek kanonik düğüm)
    c2 = await resolve_cluster_by_entity(db, "trump hakkında başka", create=False)
    assert c2 is not None
    assert c2.cluster_key == "person:trump"


async def test_resolve_no_entity_returns_none(test_db_session):
    db = test_db_session
    assert await resolve_cluster_by_entity(db, "", create=True) is None
    # eşleşen korpus entity'si yok → çapa yok → None (jenerik sorgu artefakt-küme almaz)
    assert await resolve_cluster_by_entity(db, "qwzx yokk zzz", create=True) is None
