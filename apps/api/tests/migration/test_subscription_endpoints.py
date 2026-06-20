"""Integration — Faz 2b abonelik okuma/yönetim + alert gate (testcontainers).

GET /app/me/clusters (my_clusters) + unsubscribe servisi + detect_trend_alerts
subscription-gate. Endpoint fonksiyonları doğrudan çağrılır (test_notifications
deseni); commit'siz yollar → fixture per-test rollback uyumlu.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.api.app_me import my_clusters
from app.core.research_clustering import canonical_cluster_key
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


# =============================================================================
# #12 — my_clusters trend-enrichment (spark) dalı. trends.enabled=True iken
# SubscribedClusterItem.spark/trend_state/article_count_window dolar; metrik-
# eşleşmeyen kümede 'quiet' + spark=[] fallback. (Önceden yalnız trends.enabled
# =False yolu test ediliyordu.)
# =============================================================================


async def _trend_src(db) -> uuid.UUID:
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


async def _trend_art(db, sid, pub, norm: str, etype: str) -> None:
    aid = uuid.uuid4()
    h = aid.hex
    await db.execute(
        text(
            "INSERT INTO articles (id, source_id, canonical_url, source_url, title, "
            "content_hash, title_hash, published_at) VALUES (:id, :sid, :u, :u, 't', :h, :h, :p)"
        ),
        {"id": aid, "sid": sid, "u": f"https://x/{h}", "h": h, "p": pub},
    )
    await db.execute(
        text(
            "INSERT INTO entities (article_id, entity_text, entity_normalized, entity_type) "
            "VALUES (:a, :t, :n, :et)"
        ),
        {"a": aid, "t": norm, "n": norm, "et": etype},
    )


async def _cluster_with_key(db, key: str, name: str) -> uuid.UUID:
    cid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO research_clusters (id, cluster_key, cluster_type, canonical_name) "
            "VALUES (:id, :k, 'person', :n)"
        ),
        {"id": cid, "k": key, "n": name},
    )
    return cid


def _enable_trends(monkeypatch):
    """settings_store.get_bool('trends.enabled') → True (yalnız bu key)."""
    from app.shared.runtime_config.settings_store import settings_store

    async def _get_bool(db, key, default=False):
        return True if key == "trends.enabled" else default

    monkeypatch.setattr(settings_store, "get_bool", _get_bool)


async def test_my_clusters_spark_populated_when_trends_enabled(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    key = canonical_cluster_key("person", "özgür özel")  # "person:ozgur-ozel"
    cid = await _cluster_with_key(db, key, "Özgür Özel")
    await auto_subscribe(db, uid, cid)

    # Korpus: son 24 saatte "özgür özel" person haberleri → trend_metrics spark üretir.
    s1 = await _trend_src(db)
    win_start = datetime.now(UTC) - timedelta(hours=24)
    for i in range(6):
        await _trend_art(db, s1, win_start + timedelta(hours=2 + i * 3), "özgür özel", "person")

    _enable_trends(monkeypatch)
    resp = await my_clusters(user=SimpleNamespace(id=uid), db=db)  # type: ignore[arg-type]

    assert resp.total == 1
    item = resp.clusters[0]
    assert item.cluster_id == str(cid)
    # Spark dolu (12 bucket) + trend alanları set (eşleşen metrik).
    assert item.spark and len(item.spark) == 12
    assert sum(item.spark) == 6
    assert item.trend_state in {"breaking", "developing", "stable", "fading"}
    assert item.article_count_window == 6


async def test_my_clusters_quiet_fallback_when_no_metric(test_db_session, monkeypatch):
    """trends.enabled=True ama küme anahtarı korpusta yok → 'quiet' + spark=[] fallback."""
    db = test_db_session
    uid = await _user(db)
    # Korpusla eşleşmeyen anahtar (hiç entity seed edilmedi).
    cid = await _cluster_with_key(db, canonical_cluster_key("person", "olmayan kisi"), "Olmayan")
    await auto_subscribe(db, uid, cid)

    _enable_trends(monkeypatch)
    resp = await my_clusters(user=SimpleNamespace(id=uid), db=db)  # type: ignore[arg-type]

    item = resp.clusters[0]
    assert item.trend_state == "quiet"
    assert item.spark == []  # default korunur (eşleşme yok)
    assert item.article_count_window == 0
