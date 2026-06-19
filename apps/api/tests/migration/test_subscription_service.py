"""Integration — Faz 2a auto_subscribe servis mantığı (testcontainers).

Idempotency (canlı slot) + opt-out'a saygı (çıkılan kümeye yeniden abone
YAPMAZ). auto_subscribe commit etmez → test fixture per-test rollback uyumlu.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.generations.subscriptions import auto_subscribe
from sqlalchemy import text

pytestmark = pytest.mark.integration


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
            "VALUES (:id, :k, 'topic', 'Asgari Ücret')"
        ),
        {"id": cid, "k": f"topic:{cid.hex[:10]}"},
    )
    return cid


async def _count(db, uid, *, live_only=False) -> int:
    sql = "SELECT count(*) FROM user_cluster_subscriptions WHERE user_id = :u"
    if live_only:
        sql += " AND unsubscribed_at IS NULL"
    return (await db.execute(text(sql), {"u": uid})).scalar()


async def test_auto_subscribe_creates_then_idempotent(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)

    assert await auto_subscribe(db, uid, cid) is True
    assert await auto_subscribe(db, uid, cid) is False  # canlı slot dolu
    assert await _count(db, uid) == 1
    assert await _count(db, uid, live_only=True) == 1


async def test_auto_subscribe_respects_optout(test_db_session):
    """Kullanıcı çıktıysa tekrar sorgulamak yeniden abone YAPMAZ (opt-out kalıcı)."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)

    assert await auto_subscribe(db, uid, cid) is True
    # kullanıcı kümeden çıktı (soft)
    await db.execute(
        text(
            "UPDATE user_cluster_subscriptions SET status='unsubscribed', "
            "unsubscribed_at = NOW() WHERE user_id = :u AND cluster_id = :c"
        ),
        {"u": uid, "c": cid},
    )
    # tekrar atama → yeniden abone OLMAZ
    assert await auto_subscribe(db, uid, cid) is False
    assert await _count(db, uid) == 1  # yalnız eski (unsubscribed) satır
    assert await _count(db, uid, live_only=True) == 0


async def test_auto_subscribe_source_recorded(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)

    assert await auto_subscribe(db, uid, cid, source="auto_query") is True
    src = (
        await db.execute(
            text(
                "SELECT source FROM user_cluster_subscriptions "
                "WHERE user_id = :u AND cluster_id = :c"
            ),
            {"u": uid, "c": cid},
        )
    ).scalar()
    assert src == "auto_query"
