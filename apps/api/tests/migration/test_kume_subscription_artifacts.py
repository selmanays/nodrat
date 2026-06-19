"""Integration — Faz 0 küme abonelik + artefakt şema invariant'ları (testcontainers).

Partial-unique (kullanıcı başına küme başına TEK canlı abonelik) + FK CASCADE +
artefakt↔revizyon zinciri. Davranış (auto-subscribe, generation→artifact) Faz 2-3'te;
buradaki test yalnız şema/constraint katmanını kapsar (idempotency ON CONFLICT
deseni — test_notifications.py ile aynı stil, fixture transaction-uyumlu).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def _user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:id, :e, 'x')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@test.local"},
    )
    return uid


async def _cluster(db, name: str = "Asgari Ücret") -> uuid.UUID:
    cid = uuid.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO research_clusters (id, cluster_key, cluster_type, canonical_name)
            VALUES (:id, :k, 'topic', :n)
            """
        ),
        {"id": cid, "k": f"topic:{cid.hex[:10]}", "n": name},
    )
    return cid


async def _subscribe(db, uid: uuid.UUID, cid: uuid.UUID) -> int:
    """Faz 2 auto-subscribe deseni: canlı slota idempotent upsert."""
    res = await db.execute(
        text(
            """
            INSERT INTO user_cluster_subscriptions (user_id, cluster_id, status, source)
            VALUES (:u, :c, 'active', 'auto_query')
            ON CONFLICT (user_id, cluster_id) WHERE unsubscribed_at IS NULL
            DO NOTHING
            """
        ),
        {"u": uid, "c": cid},
    )
    return res.rowcount


async def test_subscription_live_slot_idempotent(test_db_session):
    """Aynı (user, cluster) 2. canlı abonelik → ON CONFLICT DO NOTHING (tek satır)."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)

    assert await _subscribe(db, uid, cid) == 1
    assert await _subscribe(db, uid, cid) == 0  # canlı slot dolu → eklenmez

    live = (
        await db.execute(
            text(
                "SELECT count(*) FROM user_cluster_subscriptions "
                "WHERE user_id = :u AND unsubscribed_at IS NULL"
            ),
            {"u": uid},
        )
    ).scalar()
    assert live == 1


async def test_unsubscribe_frees_slot_then_resubscribe(test_db_session):
    """Çıkış soft-delete (satır silinmez); slot boşalınca yeniden abone olunabilir."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)

    assert await _subscribe(db, uid, cid) == 1
    # soft unsubscribe — satır KALIR (geçmiş + KVKK)
    await db.execute(
        text(
            "UPDATE user_cluster_subscriptions SET status='unsubscribed', "
            "unsubscribed_at = NOW() WHERE user_id = :u AND cluster_id = :c"
        ),
        {"u": uid, "c": cid},
    )
    assert await _subscribe(db, uid, cid) == 1  # slot boş → yeniden abone

    total = (
        await db.execute(
            text("SELECT count(*) FROM user_cluster_subscriptions WHERE user_id = :u"),
            {"u": uid},
        )
    ).scalar()
    live = (
        await db.execute(
            text(
                "SELECT count(*) FROM user_cluster_subscriptions "
                "WHERE user_id = :u AND unsubscribed_at IS NULL"
            ),
            {"u": uid},
        )
    ).scalar()
    assert total == 2  # eski (unsubscribed) + yeni (live) — satır silinmedi
    assert live == 1


async def test_subscription_user_cascade(test_db_session):
    """Kullanıcı silinince abonelik gider (KVKK CASCADE)."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    await _subscribe(db, uid, cid)

    await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
    cnt = (
        await db.execute(
            text("SELECT count(*) FROM user_cluster_subscriptions WHERE user_id = :u"),
            {"u": uid},
        )
    ).scalar()
    assert cnt == 0


async def test_artifact_revision_chain_and_cascade(test_db_session):
    """Artefakt + revizyon zinciri; artefakt silinince revizyonlar CASCADE gider."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)

    aid = uuid.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO artifacts (id, cluster_id, user_id, artifact_type)
            VALUES (:id, :c, :u, 'thread')
            """
        ),
        {"id": aid, "c": cid, "u": uid},
    )
    for seq in (1, 2):
        await db.execute(
            text(
                """
                INSERT INTO artifact_revisions
                    (artifact_id, revision_seq, content, revision_intent)
                VALUES (:a, :s, :content, :intent)
                """
            ),
            {
                "a": aid,
                "s": seq,
                "content": f"sürüm {seq}",
                "intent": "initial" if seq == 1 else "quick_shorter",
            },
        )

    # aynı revision_seq tekrar → ON CONFLICT (unique) DO NOTHING
    dup = await db.execute(
        text(
            """
            INSERT INTO artifact_revisions
                (artifact_id, revision_seq, content, revision_intent)
            VALUES (:a, 1, 'çakışma', 'system')
            ON CONFLICT (artifact_id, revision_seq) DO NOTHING
            """
        ),
        {"a": aid},
    )
    assert dup.rowcount == 0

    n = (
        await db.execute(
            text("SELECT count(*) FROM artifact_revisions WHERE artifact_id = :a"),
            {"a": aid},
        )
    ).scalar()
    assert n == 2

    # artefakt silinince revizyonlar gider (CASCADE)
    await db.execute(text("DELETE FROM artifacts WHERE id = :a"), {"a": aid})
    n2 = (
        await db.execute(
            text("SELECT count(*) FROM artifact_revisions WHERE artifact_id = :a"),
            {"a": aid},
        )
    ).scalar()
    assert n2 == 0
