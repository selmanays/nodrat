"""Integration — Faz 2b abonelik okuma/yönetim + alert gate (testcontainers).

GET /app/me/clusters (my_clusters) + unsubscribe servisi + detect_trend_alerts
subscription-gate. Endpoint fonksiyonları doğrudan çağrılır (test_notifications
deseni); commit'siz yollar → fixture per-test rollback uyumlu.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.api.app_me import my_clusters
from app.modules.generations.subscriptions import auto_subscribe, unsubscribe
from app.modules.trends.tasks.alerts import _detect_for_session
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
            "INSERT INTO research_clusters (id, cluster_key, cluster_type, canonical_name) "
            "VALUES (:id, :k, 'topic', :n)"
        ),
        {"id": cid, "k": f"topic:{cid.hex[:10]}", "n": name},
    )
    return cid


async def test_my_clusters_lists_live_excludes_unsubscribed(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    await auto_subscribe(db, uid, cid)

    user = SimpleNamespace(id=uid)
    resp = await my_clusters(user=user, db=db)  # type: ignore[arg-type]
    assert resp.total == 1
    assert resp.clusters[0].cluster_id == str(cid)
    assert resp.clusters[0].source == "auto_query"
    assert resp.clusters[0].canonical_name == "Asgari Ücret"

    # çıkınca explicit-abonelik listesinde GÖRÜNMEZ
    assert await unsubscribe(db, uid, cid) is True
    resp2 = await my_clusters(user=user, db=db)  # type: ignore[arg-type]
    assert resp2.total == 0


async def test_my_clusters_user_scoped(test_db_session):
    """Başkasının aboneliği sızmaz."""
    db = test_db_session
    uid = await _user(db)
    other = await _user(db)
    cid = await _cluster(db)
    await auto_subscribe(db, other, cid)  # başka kullanıcı abone

    resp = await my_clusters(user=SimpleNamespace(id=uid), db=db)  # type: ignore[arg-type]
    assert resp.total == 0  # ben abone değilim → boş


async def test_unsubscribe_idempotent(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    await auto_subscribe(db, uid, cid)

    assert await unsubscribe(db, uid, cid) is True
    assert await unsubscribe(db, uid, cid) is False  # zaten çıkılmış → no-op


async def test_alert_gate_targets_explicit_subscribers(test_db_session):
    """use_subscriptions=True → açık aboneye yönelir; message_clusters'a değil."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    await auto_subscribe(db, uid, cid)  # açık abonelik var; message_clusters YOK

    now = datetime.now(UTC)
    res_sub = await _detect_for_session(db, now, use_subscriptions=True)
    assert res_sub["pairs"] == 1  # abone bulundu (trend yoksa created=0)

    res_msg = await _detect_for_session(db, now, use_subscriptions=False)
    assert res_msg["pairs"] == 0  # message_clusters boş → hedef yok
