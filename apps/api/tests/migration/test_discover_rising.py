"""Integration — #1745 proaktif keşif radarı (discover_rising + public_trending).

discover_rising: rising_entities() reuse, kullanıcının ABONE kümeleri DIŞLANIR,
trends.enabled OFF → boş. public_trending: anonim, yalnız güvenli alanlar.
Yükselen senaryo gerçek now'a göre seed edilir (endpoint datetime.now(UTC) kullanır).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.api.app_me import discover_rising
from app.core.research_clustering import canonical_cluster_key
from app.modules.generations.subscriptions import auto_subscribe
from app.modules.public.search import public_trending
from sqlalchemy import text

pytestmark = pytest.mark.integration


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


async def _art(db, sid, pub, norm: str, etype: str) -> None:
    aid = uuid.uuid4()
    h = aid.hex
    await db.execute(
        text(
            "INSERT INTO articles (id, source_id, canonical_url, source_url, title, "
            "content_hash, title_hash, published_at) VALUES (:id,:sid,:u,:u,'t',:h,:h,:p)"
        ),
        {"id": aid, "sid": sid, "u": f"https://x/{h}", "h": h, "p": pub},
    )
    await db.execute(
        text(
            "INSERT INTO entities (article_id, entity_text, entity_normalized, entity_type) "
            "VALUES (:a,:t,:n,:et)"
        ),
        {"a": aid, "t": norm, "n": norm, "et": etype},
    )


async def _seed_rising(db, norm: str) -> None:
    """norm'u 'breaking' yapacak korpus: prev=2, cur=20 (son 6 saatte yoğun)."""
    s1, s2 = await _src(db), await _src(db)
    now = datetime.now(UTC)
    for i in range(2):
        await _art(db, s1 if i % 2 else s2, now - timedelta(hours=40 + i), norm, "place")
    for i in range(20):
        await _art(
            db, s1 if i % 2 else s2, now - timedelta(hours=0.25 * (i % 6) + 0.2), norm, "place"
        )


async def _seed_flat(db, norm: str) -> None:
    """Düz baseline (korpus-normalize için): prev≈cur, 24s'e yayılı → yükselmez ama
    korpus kütlesi sağlar (burst entity'ler korpus-üstü çıkabilsin)."""
    s1, s2 = await _src(db), await _src(db)
    now = datetime.now(UTC)
    for i in range(18):
        await _art(db, s1 if i % 2 else s2, now - timedelta(hours=24 + 40 * i / 60), norm, "place")
    for i in range(20):
        await _art(db, s1 if i % 2 else s2, now - timedelta(hours=1.1 * i), norm, "place")


async def _user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:id,:e,'x')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@x.test"},
    )
    return uid


async def _cluster(db, key: str, name: str) -> uuid.UUID:
    cid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO research_clusters (id, cluster_key, cluster_type, canonical_name) "
            "VALUES (:id,:k,'place',:n)"
        ),
        {"id": cid, "k": key, "n": name},
    )
    return cid


def _enable_trends(monkeypatch):
    from app.shared.runtime_config import settings_store as ss_mod

    async def _get_bool(db, key, default=False):
        return True if key == "trends.enabled" else default

    monkeypatch.setattr(ss_mod.settings_store, "get_bool", _get_bool)


async def test_discover_rising_excludes_subscribed(test_db_session, monkeypatch):
    """Abone OLUNAN yükselen küme dışlanır; abone OLUNMAYAN görünür."""
    db = test_db_session
    await _seed_flat(db, "background")  # korpus baseline → burst'ler üstte kalır
    await _seed_rising(db, "alpha")
    await _seed_rising(db, "beta")
    alpha_key = canonical_cluster_key("place", "alpha")
    beta_key = canonical_cluster_key("place", "beta")
    # alpha'ya küme + abonelik
    uid = await _user(db)
    cid = await _cluster(db, alpha_key, "Alpha")
    await auto_subscribe(db, uid, cid)

    _enable_trends(monkeypatch)
    resp = await discover_rising(user=SimpleNamespace(id=uid), db=db)  # type: ignore[arg-type]
    keys = {it.cluster_key for it in resp.data}
    assert beta_key in keys  # abone DEĞİL → görünür
    assert alpha_key not in keys  # abone → dışlandı
    # beta'nın kümesi yok → cluster_id None (kart "ara" aksiyonu)
    beta = next(it for it in resp.data if it.cluster_key == beta_key)
    assert beta.cluster_id is None
    assert beta.trend_state in {"breaking", "developing"}


async def test_discover_rising_empty_when_trends_off(test_db_session):
    """trends.enabled OFF (default) → boş (no-op)."""
    db = test_db_session
    await _seed_rising(db, "gamma")
    uid = await _user(db)
    resp = await discover_rising(user=SimpleNamespace(id=uid), db=db)  # type: ignore[arg-type]
    assert resp.data == []


async def test_public_trending_safe_fields_and_flag(test_db_session, monkeypatch):
    """trends ON → yükselenler yalnız güvenli alanlarla; OFF → boş."""
    db = test_db_session
    await _seed_flat(db, "background")  # korpus baseline
    await _seed_rising(db, "delta")
    req = SimpleNamespace(headers={}, client=None)

    # OFF (default) → boş
    off = await public_trending(request=req, db=db)  # type: ignore[arg-type]
    assert off.items == []

    # ON → delta görünür, yalnız güvenli alanlar
    _enable_trends(monkeypatch)
    on = await public_trending(request=req, db=db)  # type: ignore[arg-type]
    assert any(it.entity_name == "delta" for it in on.items)
    fields = set(on.items[0].model_dump().keys())
    assert fields == {"entity_name", "entity_type", "trend_state", "article_count"}
    assert "cluster_key" not in fields  # küme/özel veri sızmaz
