"""Integration — #1742 küme merge/reparent + canonical reconcile (testcontainers).

merge_clusters: artifacts/message_clusters/subscriptions/parent → hedefe reparent,
source soft-deprecate. UNIQUE çakışmaları (message_id+cluster_id; user+cluster live)
doğru ele alınır, opt-out korunur, idempotent. reconcile: drift gruplarını merge +
NULL canonical_id backfill (dry_run → mutation yok).
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.generations.cluster_merge import (
    merge_clusters,
    reconcile_canonical_anchors,
)
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def _user(db) -> str:
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:id, :e, 'x')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@x.test"},
    )
    return str(uid)


async def _cluster(db, key: str, name: str, cid: str | None = None) -> str:
    rid = (
        await db.execute(
            text(
                "INSERT INTO research_clusters (cluster_key, cluster_type, canonical_name, "
                "canonical_entity_id) VALUES (:k,'org',:n,:c) RETURNING id"
            ),
            {"k": key, "n": name, "c": cid},
        )
    ).scalar()
    return str(rid)


async def _sub_live(db, uid: str, clid: str) -> None:
    await db.execute(
        text(
            "INSERT INTO user_cluster_subscriptions (user_id, cluster_id, status, source) "
            "VALUES (:u,:c,'active','auto_query')"
        ),
        {"u": uid, "c": clid},
    )


async def _artifact(db, uid: str, clid: str) -> str:
    aid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO artifacts (id, cluster_id, user_id, artifact_type) "
            "VALUES (:id,:c,:u,'post')"
        ),
        {"id": aid, "c": clid, "u": uid},
    )
    return str(aid)


async def _msg_cluster(db, uid: str, clid: str, msg_id: str | None = None) -> str:
    """conv+message+message_cluster ekle; message_id döndür (çakışma testinde reuse)."""
    if msg_id is None:
        conv = uuid.uuid4()
        await db.execute(
            text("INSERT INTO conversations (id, user_id, title) VALUES (:id,:u,'t')"),
            {"id": conv, "u": uid},
        )
        m = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO messages (id, conversation_id, role, content) "
                "VALUES (:id,:c,'user','q')"
            ),
            {"id": m, "c": conv},
        )
        msg_id = str(m)
    await db.execute(
        text(
            "INSERT INTO message_clusters (message_id, cluster_id, user_id, assigned_via) "
            "VALUES (:m,:c,:u,'entity')"
        ),
        {"m": msg_id, "c": clid, "u": uid},
    )
    return msg_id


async def _is_deprecated(db, clid: str) -> bool:
    return (
        await db.execute(
            text("SELECT deprecated_at IS NOT NULL FROM research_clusters WHERE id=:i"),
            {"i": clid},
        )
    ).scalar()


async def test_merge_reparents_dependents(test_db_session):
    db = test_db_session
    u = await _user(db)
    src = await _cluster(db, "org:akp", "AKP")
    tgt = await _cluster(db, "org:adalet-ve-kalkinma-partisi", "Adalet ve Kalkınma Partisi")
    art = await _artifact(db, u, src)
    await _sub_live(db, u, src)
    await _msg_cluster(db, u, src)

    out = await merge_clusters(db, src, tgt)
    assert out["status"] == "ok"
    assert out["artifacts"] == 1 and out["subs_moved"] == 1 and out["messages_moved"] == 1
    assert out["source_deprecated"] is True

    # artefakt + abonelik + üyelik hedefe taşındı
    assert (
        await db.execute(text("SELECT cluster_id FROM artifacts WHERE id=:a"), {"a": art})
    ).scalar() == uuid.UUID(tgt)
    assert (
        await db.execute(
            text(
                "SELECT count(*) FROM user_cluster_subscriptions "
                "WHERE cluster_id=:t AND unsubscribed_at IS NULL"
            ),
            {"t": tgt},
        )
    ).scalar() == 1
    assert (
        await db.execute(
            text("SELECT count(*) FROM message_clusters WHERE cluster_id=:t"), {"t": tgt}
        )
    ).scalar() == 1
    assert await _is_deprecated(db, src) is True
    # source key hedef aliases'e iz düştü
    aliases = (
        await db.execute(text("SELECT aliases FROM research_clusters WHERE id=:t"), {"t": tgt})
    ).scalar()
    assert "org:akp" in (aliases or [])


async def test_merge_subscription_conflict_preserves_optout(test_db_session):
    """Kullanıcı HEM source HEM target'a live abone → target'taki kalır, source'taki
    soft-kapanır (partial-unique ihlali yok, opt-out izi korunur)."""
    db = test_db_session
    u = await _user(db)
    src = await _cluster(db, "org:src", "Src")
    tgt = await _cluster(db, "org:tgt", "Tgt")
    await _sub_live(db, u, src)
    await _sub_live(db, u, tgt)

    out = await merge_clusters(db, src, tgt)
    assert out["status"] == "ok"
    assert out["subs_moved"] == 0 and out["subs_closed_dup"] == 1
    # U'nun target'ta TEK live aboneliği
    assert (
        await db.execute(
            text(
                "SELECT count(*) FROM user_cluster_subscriptions "
                "WHERE user_id=:u AND cluster_id=:t AND unsubscribed_at IS NULL"
            ),
            {"u": u, "t": tgt},
        )
    ).scalar() == 1
    # source'ta live abonelik kalmadı
    assert (
        await db.execute(
            text(
                "SELECT count(*) FROM user_cluster_subscriptions "
                "WHERE cluster_id=:s AND unsubscribed_at IS NULL"
            ),
            {"s": src},
        )
    ).scalar() == 0


async def test_merge_message_conflict_dedup(test_db_session):
    """Aynı mesaj HEM source HEM target üyesi → UNIQUE(message_id,cluster_id) ihlali
    olmadan source-tarafı düşürülür."""
    db = test_db_session
    u = await _user(db)
    src = await _cluster(db, "org:src2", "Src2")
    tgt = await _cluster(db, "org:tgt2", "Tgt2")
    mid = await _msg_cluster(db, u, tgt)  # mesaj önce target'ta
    await _msg_cluster(db, u, src, msg_id=mid)  # aynı mesaj source'ta da

    out = await merge_clusters(db, src, tgt)
    assert out["status"] == "ok"
    assert out["messages_moved"] == 0 and out["messages_dropped_dup"] == 1
    rows = (
        await db.execute(
            text("SELECT cluster_id FROM message_clusters WHERE message_id=:m"), {"m": mid}
        )
    ).all()
    assert len(rows) == 1 and rows[0][0] == uuid.UUID(tgt)


async def test_merge_idempotent(test_db_session):
    db = test_db_session
    src = await _cluster(db, "org:src3", "Src3")
    tgt = await _cluster(db, "org:tgt3", "Tgt3")
    assert (await merge_clusters(db, src, tgt))["status"] == "ok"
    again = await merge_clusters(db, src, tgt)
    assert again["status"] == "noop"  # source zaten deprecated


async def test_reconcile_dry_run_then_apply(test_db_session):
    """İki küme aynı canonical'a çözülür (alias-key + canonical-key) → dry_run plan
    üretir (mutation yok); apply merge + backfill yapar."""
    db = test_db_session
    cid = (
        await db.execute(
            text(
                "INSERT INTO canonical_entities (canonical_name, entity_type, "
                "canonical_normalized, source) VALUES "
                "('Adalet ve Kalkınma Partisi','org','adalet ve kalkınma partisi','wikidata') "
                "RETURNING id"
            )
        )
    ).scalar()
    await db.execute(
        text(
            "INSERT INTO entity_aliases (alias_normalized, entity_type, canonical_id, "
            "confidence, source) VALUES ('akp','org',:c,1.000,'wikidata')"
        ),
        {"c": cid},
    )
    a = await _cluster(db, "org:akp", "AKP")  # alias-key, cid NULL
    b = await _cluster(db, "org:adalet-ve-kalkinma-partisi", "AKP")  # canonical-key, cid NULL
    u = await _user(db)
    await _sub_live(db, u, b)  # b daha çok kullanılan → merge hedefi

    dry = await reconcile_canonical_anchors(db, dry_run=True)
    assert dry["drift_groups"] == 1 and dry["merge_count"] == 1
    assert await _is_deprecated(db, a) is False  # dry_run mutasyon YOK
    assert await _is_deprecated(db, b) is False

    res = await reconcile_canonical_anchors(db, dry_run=False)
    assert res["merge_count"] == 1
    # a, b'ye merge edildi; b hayatta + canonical_id backfill
    assert await _is_deprecated(db, a) is True
    assert await _is_deprecated(db, b) is False
    assert (
        await db.execute(
            text("SELECT canonical_entity_id FROM research_clusters WHERE id=:b"), {"b": b}
        )
    ).scalar() == cid
