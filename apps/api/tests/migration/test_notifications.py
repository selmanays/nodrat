"""Integration — #1581 C user_notifications şema + endpoint read-path (testcontainers).

Migration UNIQUE(dedupe_key) idempotency + /app/me/notifications list/read mantığı.
Beat detect_trend_alerts uçtan-uca akışı prod canary'de doğrulanır (message_clusters
→ messages → conversations derin FK zinciri seed-ağır); buradaki test şema invariant'ı
+ kullanıcı okuma yolunu kapsar.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.api.app_me import MarkReadBody, mark_notifications_read, my_notifications
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def _user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:id, :e, 'x')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@test.local"},
    )
    return uid


async def _notif(db, uid: uuid.UUID, dedupe: str, title: str = "t") -> int:
    res = await db.execute(
        text(
            """
            INSERT INTO user_notifications (user_id, type, cluster_key, title, dedupe_key)
            VALUES (:uid, 'trend_alert', 'org:chp', :t, :dk)
            ON CONFLICT (dedupe_key) DO NOTHING
            """
        ),
        {"uid": uid, "t": title, "dk": dedupe},
    )
    return res.rowcount


async def test_dedupe_unique_constraint(test_db_session):
    """Aynı dedupe_key 2. kez → ON CONFLICT DO NOTHING (idempotent, tek satır)."""
    db = test_db_session
    uid = await _user(db)
    assert await _notif(db, uid, "k1") == 1
    assert await _notif(db, uid, "k1") == 0  # dedupe → eklenmez
    assert await _notif(db, uid, "k2") == 1  # farklı key → eklenir
    cnt = (
        await db.execute(
            text("SELECT count(*) FROM user_notifications WHERE user_id = :u"), {"u": uid}
        )
    ).scalar()
    assert cnt == 2


async def test_notifications_endpoint_list_and_read(test_db_session):
    db = test_db_session
    uid = await _user(db)
    other = await _user(db)
    await _notif(db, uid, "a", "Bildirim A")
    await _notif(db, uid, "b", "Bildirim B")
    await _notif(db, other, "c", "Başkasının")  # cross-user — görünmemeli

    user = SimpleNamespace(id=uid)
    resp = await my_notifications(user=user, db=db, limit=30, unread_only=False)  # type: ignore[arg-type]
    assert resp.unread_count == 2
    titles = {n.title for n in resp.notifications}
    assert titles == {"Bildirim A", "Bildirim B"}  # cross-user sızmaz
    assert all(n.read is False for n in resp.notifications)

    # tümünü okundu işaretle
    out = await mark_notifications_read(user=user, db=db, body=MarkReadBody(ids=None))  # type: ignore[arg-type]
    assert out["unread_count"] == 0
    resp2 = await my_notifications(user=user, db=db, unread_only=True)  # type: ignore[arg-type]
    assert resp2.unread_count == 0
    assert resp2.notifications == []
